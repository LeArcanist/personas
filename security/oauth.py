from authlib.integrations.starlette_client import OAuth

oauth = OAuth()

oauth.register(
    name="google",
    client_id="761260701390-impffjtj4noo4bvcgn5ff1duvk6rr066.apps.googleusercontent.com",
    #client_secret="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",
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={
        "scope": "openid email profile"
    },
)