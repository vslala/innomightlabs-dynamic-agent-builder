"""
Tests for encryption utilities.
"""

import pytest

from src.crypto import encrypt, decrypt, encrypt_secret_fields, decrypt_secret_fields
from src.form_models import Form, FormInput, FormInputType


class TestEncryption:
    """Tests for basic encryption/decryption."""

    def test_encrypt_decrypt_roundtrip(self):
        """Test that encrypting then decrypting returns original value."""
        original = "my-secret-api-key-123"
        encrypted = encrypt(original)
        decrypted = decrypt(encrypted)

        assert decrypted == original
        assert encrypted != original

    def test_encrypt_produces_different_output(self):
        """Test that encrypted value differs from original."""
        original = "secret-value"
        encrypted = encrypt(original)

        assert encrypted != original
        assert len(encrypted) > len(original)


class TestEncryptSecretFields:
    """Tests for schema-based field encryption."""

    @pytest.fixture
    def sample_form(self) -> Form:
        """Create a sample form schema with mixed field types."""
        return Form(
            form_name="Test Form",
            submit_path="/test",
            form_inputs=[
                FormInput(
                    label="Name",
                    name="name",
                    input_type=FormInputType.TEXT,
                ),
                FormInput(
                    label="Description",
                    name="description",
                    input_type=FormInputType.TEXT_AREA,
                ),
                FormInput(
                    label="API Key",
                    name="api_key",
                    input_type=FormInputType.PASSWORD,
                ),
                FormInput(
                    label="Secret Token",
                    name="secret_token",
                    input_type=FormInputType.PASSWORD,
                ),
            ],
        )

    def test_encrypts_password_fields_only(self, sample_form: Form):
        """Test that only PASSWORD fields are encrypted."""
        data = {
            "name": "Test Agent",
            "description": "A test agent",
            "api_key": "key-123",
            "secret_token": "token-456",
        }

        encrypted = encrypt_secret_fields(sample_form, data)

        # Non-password fields unchanged
        assert encrypted["name"] == "Test Agent"
        assert encrypted["description"] == "A test agent"

        # Password fields encrypted
        assert encrypted["api_key"] != "key-123"
        assert encrypted["secret_token"] != "token-456"

    def test_decrypt_restores_original_values(self, sample_form: Form):
        """Test that decrypt_secret_fields restores original values."""
        original_data = {
            "name": "Test Agent",
            "description": "A test agent",
            "api_key": "key-123",
            "secret_token": "token-456",
        }

        encrypted = encrypt_secret_fields(sample_form, original_data)
        decrypted = decrypt_secret_fields(sample_form, encrypted)

        assert decrypted == original_data

    def test_does_not_modify_original_dict(self, sample_form: Form):
        """Test that encryption does not modify the original dictionary."""
        original_data = {
            "name": "Test Agent",
            "api_key": "key-123",
        }
        original_key = original_data["api_key"]

        encrypt_secret_fields(sample_form, original_data)

        assert original_data["api_key"] == original_key

    def test_handles_missing_fields(self, sample_form: Form):
        """Test that missing fields are handled gracefully."""
        data = {
            "name": "Test Agent",
            # api_key and secret_token are missing
        }

        encrypted = encrypt_secret_fields(sample_form, data)

        assert encrypted["name"] == "Test Agent"
        assert "api_key" not in encrypted
        assert "secret_token" not in encrypted
