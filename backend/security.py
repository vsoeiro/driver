import json
from cryptography.fernet import Fernet


class TokenEncryption:
    """Encrypt and decrypt token data using Fernet symmetric encryption."""

    def __init__(self, encryption_key: str):
        """
        Initialize the TokenEncryption with a Fernet key.

        Parameters
        ----------
        encryption_key : str
            The Fernet encryption key as a string.
        """
        self._fernet = Fernet(encryption_key.encode())

    def encrypt(self, data: dict) -> str:
        """
        Encrypt a dictionary to a base64-encoded string.

        Parameters
        ----------
        data : dict
            The data to be encrypted.

        Returns
        -------
        str
            The base64-encoded encrypted string.
        """
        json_data = json.dumps(data)
        return self._fernet.encrypt(json_data.encode()).decode()

    def decrypt(self, token: str) -> dict:
        """
        Decrypt a Fernet-encrypted token back to a dictionary.

        Parameters
        ----------
        token : str
            The encrypted token string.

        Returns
        -------
        dict
            The decrypted data as a dictionary.

        Raises
        ------
        cryptography.fernet.InvalidToken
            If the token is invalid or corrupted.
        """
        decrypted_data = self._fernet.decrypt(token.encode())
        return json.loads(decrypted_data.decode())
