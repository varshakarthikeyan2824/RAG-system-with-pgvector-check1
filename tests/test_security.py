import pytest

from src.security import hash_password, validate_password, verify_password


def test_password_is_hashed():
    password = "MyStrongPassword123!"
    hashed = hash_password(password)

    assert hashed != password
    assert hashed.startswith("$argon2id$")


def test_correct_password_is_verified():
    password = "MyStrongPassword123!"
    hashed = hash_password(password)

    assert verify_password(password, hashed) is True


def test_incorrect_password_is_rejected():
    hashed = hash_password("MyStrongPassword123!")

    assert verify_password("WrongPassword123!", hashed) is False


def test_same_password_produces_different_hashes():
    password = "MyStrongPassword123!"

    first_hash = hash_password(password)
    second_hash = hash_password(password)

    assert first_hash != second_hash
    assert verify_password(password, first_hash)
    assert verify_password(password, second_hash)


def test_reject_short_password():
    with pytest.raises(ValueError):
        validate_password("Short123!")


def test_accept_15_character_password():
    validate_password("StrongPass12345")


def test_accept_long_password():
    validate_password("A" * 100)


def test_reject_password_over_128_characters():
    with pytest.raises(ValueError):
        validate_password("A" * 129)


def test_reject_common_password():
    with pytest.raises(ValueError):
        validate_password("password123")


def test_reject_case_insensitive_common_password():
    with pytest.raises(ValueError):
        validate_password("PASSWORD123")
