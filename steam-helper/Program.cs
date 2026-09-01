using System.Text;
using System.Text.Json;
using SteamKit2;
using SteamKit2.Authentication;

const uint Bb3AppId = 1016950;

if (args.Length == 0)
{
    Console.Error.WriteLine("Usage:");
    Console.Error.WriteLine("  BB3SteamAuth bootstrap");
    Console.Error.WriteLine("  BB3SteamAuth ticket");
    return 1;
}

return args[0].ToLowerInvariant() switch
{
    "bootstrap" => await BootstrapAsync(),
    "ticket" => await TicketAsync(),
    _ => Fail("Unknown command. Use bootstrap or ticket.")
};

static int Fail(string message)
{
    Console.Error.WriteLine(message);
    return 1;
}

static async Task<int> BootstrapAsync()
{
    var username = Environment.GetEnvironmentVariable("STEAM_USERNAME");
    var password = Environment.GetEnvironmentVariable("STEAM_PASSWORD");

    if (string.IsNullOrWhiteSpace(username) || string.IsNullOrWhiteSpace(password))
        return Fail("Set STEAM_USERNAME and STEAM_PASSWORD.");

    using var steam = new SteamSession();
    await steam.ConnectAsync();

    var authSession =
        await steam.Client.Authentication.BeginAuthSessionViaCredentialsAsync(
            new AuthSessionDetails
            {
                Username = username,
                Password = password,
                IsPersistentSession = true,
                GuardData = Environment.GetEnvironmentVariable("STEAM_GUARD_DATA"),
                Authenticator = new ConsoleAuthenticator(),
            }
        );

    var poll = await authSession.PollingWaitForResultAsync();

    if (string.IsNullOrWhiteSpace(poll.RefreshToken))
        throw new InvalidOperationException("No Steam refresh token returned.");

    Console.WriteLine(JsonSerializer.Serialize(new
    {
        username,
        refreshToken = poll.RefreshToken,
        guardData = poll.NewGuardData
    }));

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
