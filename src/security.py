from pwdlib import PasswordHash

password_hash = PasswordHash.recommended()

COMMON_PASSWORDS = {
    "password",
    "password123",
    "123456789",
    "123456789012345",
    "qwerty123",
    "admin123",
    "welcome123",
}


def validate_password(password: str) -> None:
    if len(password) < 15:
        raise ValueError("Password must contain at least 15 characters")

    if len(password) > 128:
        raise ValueError("Password cannot exceed 128 characters")

    if password.lower() in COMMON_PASSWORDS:
        raise ValueError("Password is too common")


def hash_password(password: str) -> str:
    validate_password(password)
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)
