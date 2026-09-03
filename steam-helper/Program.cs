using System.Text;
using System.Text.Json;
using SteamKit2;
using SteamKit2.Authentication;

const uint Bb3AppId = 1016950;

if (args.Length == 0)
{
    Console.Error.WriteLine("Usage:");
    Console.Error.WriteLine("  BB3SteamAuth bootstrap");
    Console.Error.WriteLine("  BB3SteamAuth bootstrap-web");
    Console.Error.WriteLine("  BB3SteamAuth ticket");
    return 1;
}

return args[0].ToLowerInvariant() switch
{
    "bootstrap" => await BootstrapAsync(false),
    "bootstrap-web" => await BootstrapAsync(true),
    "ticket" => await TicketAsync(),
    _ => Fail("Unknown command. Use bootstrap or ticket.")
};

static int Fail(string message)
{
    Console.Error.WriteLine(message);
    return 1;
}

static async Task<int> BootstrapAsync(bool webMode)
{
    string? username;
    string? password;
    string? guardData;
    if (webMode)
    {
        var line = await Console.In.ReadLineAsync();
        if (line is null)
            return Fail("Web authentication input was closed before credentials were supplied.");
        using var credentials = JsonDocument.Parse(line);
        var root = credentials.RootElement;
        username = root.TryGetProperty("username", out var usernameValue)
            ? usernameValue.GetString()
            : null;
        password = root.TryGetProperty("password", out var passwordValue)
            ? passwordValue.GetString()
            : null;
        guardData = root.TryGetProperty("guardData", out var guardDataValue)
            ? guardDataValue.GetString()
            : null;
    }
    else
    {
        username = Environment.GetEnvironmentVariable("STEAM_USERNAME");
        password = Environment.GetEnvironmentVariable("STEAM_PASSWORD");
        guardData = Environment.GetEnvironmentVariable("STEAM_GUARD_DATA");
    }

    if (string.IsNullOrWhiteSpace(username) || string.IsNullOrWhiteSpace(password))
        return Fail(webMode
            ? "Steam username and password are required."
            : "Set STEAM_USERNAME and STEAM_PASSWORD.");

    using var steam = new SteamSession();
    await steam.ConnectAsync();

    IAuthenticator authenticator = webMode
        ? new JsonLineAuthenticator()
        : new ConsoleAuthenticator();
    var authSession =
        await steam.Client.Authentication.BeginAuthSessionViaCredentialsAsync(
            new AuthSessionDetails
            {
                Username = username,
                Password = password,
                IsPersistentSession = true,
                GuardData = guardData,
                Authenticator = authenticator,
            }
        );

    var poll = await authSession.PollingWaitForResultAsync();

    if (string.IsNullOrWhiteSpace(poll.RefreshToken))
        throw new InvalidOperationException("No Steam refresh token returned.");

    if (webMode)
    {
        Console.WriteLine(JsonSerializer.Serialize(new
        {
            eventType = "auth_state",
            username,
            refreshToken = poll.RefreshToken,
            guardData = poll.NewGuardData
        }));
    }
    else
    {
        Console.WriteLine(JsonSerializer.Serialize(new
        {
            username,
            refreshToken = poll.RefreshToken,
            guardData = poll.NewGuardData
        }));
    }
    Console.Out.Flush();

    return 0;
}

static async Task<int> TicketAsync()
{
    var username = Environment.GetEnvironmentVariable("STEAM_USERNAME");
    var refreshToken = Environment.GetEnvironmentVariable("STEAM_REFRESH_TOKEN");

    if (string.IsNullOrWhiteSpace(username) || string.IsNullOrWhiteSpace(refreshToken))
        return Fail("Set STEAM_USERNAME and STEAM_REFRESH_TOKEN.");

    using var steam = new SteamSession();

    var loggedOnTcs =
        new TaskCompletionSource<SteamUser.LoggedOnCallback>(
            TaskCreationOptions.RunContinuationsAsynchronously
        );

    steam.Callbacks.Subscribe<SteamUser.LoggedOnCallback>(
        callback => loggedOnTcs.TrySetResult(callback)
    );

    await steam.ConnectAsync();

    steam.User.LogOn(new SteamUser.LogOnDetails
    {
        Username = username,
        AccessToken = refreshToken,
        ShouldRememberPassword = true,
    });

    var loggedOn = await loggedOnTcs.Task.WaitAsync(TimeSpan.FromSeconds(30));

    if (loggedOn.Result != EResult.OK)
        throw new InvalidOperationException(
            $"Steam logon failed: {loggedOn.Result} / {loggedOn.ExtendedResult}"
        );

    var authTicket =
        steam.Client.GetHandler<SteamAuthTicket>()
        ?? throw new InvalidOperationException("SteamAuthTicket unavailable.");

    var ticketInfo =
        await authTicket
            .GetAuthSessionTicket(Bb3AppId)
            .WaitAsync(TimeSpan.FromSeconds(30));

    // BB3 expects Base64(ASCII(UPPERCASE_HEX(raw Steam ticket))).
    var ticketHex = Convert.ToHexString(ticketInfo.Ticket);
    var authToken = Convert.ToBase64String(
        Encoding.ASCII.GetBytes(ticketHex)
    );

    Console.WriteLine(JsonSerializer.Serialize(new
    {
        steamId = steam.Client.SteamID.ConvertToUInt64().ToString(),
        appId = Bb3AppId,
        authToken
    }));
    Console.Out.Flush();

    // Keep ticket/session alive while BB3 validates and uses it.
    Console.Error.WriteLine("Steam ticket active. Waiting for caller to release it...");
    await Console.In.ReadLineAsync();
    Console.Error.WriteLine("Releasing Steam session.");

    return 0;
}

sealed class ConsoleAuthenticator : IAuthenticator
{
    public Task<string> GetDeviceCodeAsync(bool previousCodeWasIncorrect)
    {
        Console.Error.Write("Steam Guard code: ");
        return Task.FromResult(Console.ReadLine()?.Trim() ?? "");
    }

    public Task<string> GetEmailCodeAsync(string email, bool previousCodeWasIncorrect)
    {
        Console.Error.Write($"Steam email code for {email}: ");
        return Task.FromResult(Console.ReadLine()?.Trim() ?? "");
    }

    public Task<bool> AcceptDeviceConfirmationAsync()
    {
        Console.Error.WriteLine("Approve the sign-in in Steam Mobile, then press Enter.");
        Console.ReadLine();
        return Task.FromResult(true);
    }
}

sealed class JsonLineAuthenticator : IAuthenticator
{
    public Task<string> GetDeviceCodeAsync(bool previousCodeWasIncorrect) =>
        ReadCodeAsync("device_code", null, previousCodeWasIncorrect);

    public Task<string> GetEmailCodeAsync(string email, bool previousCodeWasIncorrect) =>
        ReadCodeAsync("email_code", email, previousCodeWasIncorrect);

    public async Task<bool> AcceptDeviceConfirmationAsync()
    {
        WriteEvent(new
        {
            eventType = "steam_guard_required",
            method = "device_confirmation"
        });
        using var response = await ReadResponseAsync();
        var root = response.RootElement;
        ThrowIfCancelled(root);
        return root.TryGetProperty("approved", out var approved) && approved.GetBoolean();
    }

    private static async Task<string> ReadCodeAsync(
        string method,
        string? email,
        bool previousCodeWasIncorrect)
    {
        WriteEvent(new
        {
            eventType = "steam_guard_required",
            method,
            email,
            previousCodeWasIncorrect
        });
        using var response = await ReadResponseAsync();
        var root = response.RootElement;
        ThrowIfCancelled(root);
        if (!root.TryGetProperty("code", out var code) || string.IsNullOrWhiteSpace(code.GetString()))
            throw new InvalidOperationException("Steam Guard response did not contain a code.");
        return code.GetString()!.Trim();
    }

    private static void WriteEvent(object value)
    {
        Console.WriteLine(JsonSerializer.Serialize(value));
        Console.Out.Flush();
    }

    private static async Task<JsonDocument> ReadResponseAsync()
    {
        var line = await Console.In.ReadLineAsync();
        if (line is null)
            throw new OperationCanceledException("Steam authentication input was closed.");
        try
        {
            return JsonDocument.Parse(line);
        }
        catch (JsonException error)
        {
            throw new InvalidOperationException("Steam authentication response was not valid JSON.", error);
        }
    }

    private static void ThrowIfCancelled(JsonElement response)
    {
        if (response.TryGetProperty("cancel", out var cancel) && cancel.ValueKind == JsonValueKind.True)
            throw new OperationCanceledException("Steam authentication was cancelled.");
    }
}

sealed class SteamSession : IDisposable
{
    private readonly CancellationTokenSource _cts = new();
    private readonly TaskCompletionSource<bool> _connectedTcs =
        new(TaskCreationOptions.RunContinuationsAsynchronously);

    private Task? _callbackLoop;

    public SteamClient Client { get; } = new();
    public CallbackManager Callbacks { get; }
    public SteamUser User { get; }

    public SteamSession()
    {
        Callbacks = new CallbackManager(Client);
        User = Client.GetHandler<SteamUser>()
            ?? throw new InvalidOperationException("SteamUser unavailable.");

        Callbacks.Subscribe<SteamClient.ConnectedCallback>(
            _ => _connectedTcs.TrySetResult(true)
        );
    }

    public async Task ConnectAsync()
    {
        _callbackLoop = Task.Run(() =>
        {
            while (!_cts.IsCancellationRequested)
                Callbacks.RunWaitCallbacks(TimeSpan.FromMilliseconds(250));
        });

        Client.Connect();
        await _connectedTcs.Task.WaitAsync(TimeSpan.FromSeconds(30));
    }

    public void Dispose()
    {
        _cts.Cancel();
        try { Client.Disconnect(); } catch { }

        if (_callbackLoop is not null)
        {
            try { _callbackLoop.Wait(TimeSpan.FromSeconds(2)); } catch { }
        }

        _cts.Dispose();
    }
}
