import os
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

class ERPSecurity:
    def __init__(self):
        pass

    def encrypt_file(self, file_path, public_key_pem):
        """Encrypts a file using the user's public key."""
        with open(file_path, 'rb') as f:
            data = f.read()

        # Generate a symmetric key for this file
        aes_key = os.urandom(32)
        iv = os.urandom(16)

        # Encrypt the data with AES
        cipher = Cipher(algorithms.AES(aes_key), modes.CFB(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        encrypted_data = encryptor.update(data) + encryptor.finalize()

        # Encrypt the AES key with the public key
        public_key = serialization.load_pem_public_key(public_key_pem.encode(), backend=default_backend())
        encrypted_aes_key = public_key.encrypt(
            aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )

        # Save the encrypted file (.erp)
        vault_path = file_path + ".erp"
        with open(vault_path, 'wb') as f:
            f.write(iv)
            f.write(encrypted_aes_key)
            f.write(encrypted_data)

        # Delete the original file
        if os.path.exists(file_path):
            os.remove(file_path)

        return vault_path

    def decrypt_file(self, vault_path, encrypted_private_key, password):
        """Decrypts a file using the user's private key."""
        with open(vault_path, 'rb') as f:
            iv = f.read(16)
            encrypted_aes_key = f.read(256) # Assuming 2048-bit RSA key
            encrypted_data = f.read()

        # Load and decrypt the private key
        private_key = serialization.load_pem_private_key(
            encrypted_private_key,
            password=password.encode() if password else None,
            backend=default_backend()
        )

        # Decrypt the AES key
        aes_key = private_key.decrypt(
            encrypted_aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )

        # Decrypt the data
        cipher = Cipher(algorithms.AES(aes_key), modes.CFB(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        decrypted_data = decryptor.update(encrypted_data) + decryptor.finalize()

        return decrypted_data
