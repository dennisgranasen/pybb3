from bb3 import BB3Client, BB3RequestError 

with BB3Client.from_steam() as client:
    while True:
        try:
            client.login()
            print("BB3 login succeded")
            break
        except BB3RequestError as e:
            print(f"BB3 login failed: {e}")

    print("Creating team race 2")
    team_id = client.create_team(
        name="pybb3 Test",
        race_id=2,
    )
    print(team_id)
print("Bye.")
