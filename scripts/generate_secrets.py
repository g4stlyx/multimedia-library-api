import secrets


def generate_urlsafe_secret(byte_count: int = 64) -> str:
    return secrets.token_urlsafe(byte_count)


def main() -> None:
    jwt_secret = generate_urlsafe_secret()
    password_pepper = generate_urlsafe_secret()

    print("JWT_SECRET_KEY=" + jwt_secret)
    print("PASSWORD_PEPPER=" + password_pepper)


if __name__ == "__main__":
    main()
