"""
Script to encrypt prompts for secure storage.

This script helps encrypt prompts for production deployment.
Encrypted prompts can be stored in environment variables.

Usage:
    python scripts/encrypt_prompts.py
    
    This will generate encrypted versions of all prompts that can be
    added to your .env file or environment variables.
"""

import os
import sys
from cryptography.fernet import Fernet

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.config.prompts import _derive_prompt_key


def encrypt_prompt(prompt_text: str) -> str:
    """
    Encrypt a prompt string using the same key derivation as the prompts module.
    
    Args:
        prompt_text: Plain text prompt to encrypt
        
    Returns:
        Base64-encoded encrypted prompt
        
    Raises:
        ValueError: If VIVA_HMAC_SECRET is not set or invalid
    """
    # Check that HMAC_SECRET is set
    hmac_secret = os.getenv("VIVA_HMAC_SECRET")
    if not hmac_secret or hmac_secret == "DEVELOPMENT-ONLY-CHANGE-ME":
        raise ValueError(
            "VIVA_HMAC_SECRET must be set in environment variables or .env file. "
            "This is required for prompt encryption. Set it before running this script."
        )
    
    key = _derive_prompt_key()
    f = Fernet(key)
    encrypted = f.encrypt(prompt_text.encode('utf-8'))
    return encrypted.decode('utf-8')


def main():
    """
    Main function to encrypt prompts.
    
    Uses the same default prompts as defined in shared.config.prompts
    to ensure consistency.
    """
    # Import default prompts from the prompts module
    from shared.config.prompts import (
        _DEFAULT_SYSTEM_PROMPT,
        _DEFAULT_MAIN_QUESTION_INSTR,
        _DEFAULT_FOLLOWUP_QUESTION_INSTR,
        _DEFAULT_FEEDBACK_BLOCK_INSTR,
        _DEFAULT_SHORT_PROMPT_TTS,
    )
    
    prompts = {
        "SYSTEM_PROMPT": _DEFAULT_SYSTEM_PROMPT,
        "MAIN_QUESTION_INSTR": _DEFAULT_MAIN_QUESTION_INSTR,
        "FOLLOWUP_QUESTION_INSTR": _DEFAULT_FOLLOWUP_QUESTION_INSTR,
        "FEEDBACK_BLOCK_INSTR": _DEFAULT_FEEDBACK_BLOCK_INSTR,
        "SHORT_PROMPT_TTS": _DEFAULT_SHORT_PROMPT_TTS,
    }
    
    print("=" * 80)
    print("PROMPT ENCRYPTION TOOL")
    print("=" * 80)
    print("\nThis tool encrypts business logic prompts for secure storage.")
    print("Encrypted prompts will be loaded automatically at runtime.\n")
    
    try:
        print("Encrypted prompts (add these to your .env file):\n")
        
        for prompt_name, prompt_text in prompts.items():
            encrypted = encrypt_prompt(prompt_text)
            print(f"PROMPT_{prompt_name}_ENCRYPTED={encrypted}")
            print()
        
        print("=" * 80)
        print("\n✓ Successfully encrypted all prompts!")
        print("\nNext steps:")
        print("1. Copy the PROMPT_*_ENCRYPTED variables above")
        print("2. Add them to your .env file or environment variables")
        print("3. Ensure VIVA_HMAC_SECRET is set (required for decryption)")
        print("4. Restart your application to load encrypted prompts")
        print("=" * 80)
        
    except ValueError as e:
        print(f"\n❌ Error: {e}\n")
        print("Please set VIVA_HMAC_SECRET in your .env file before running this script.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()

