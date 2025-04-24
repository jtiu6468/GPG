from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
import asyncio
import nest_asyncio
import subprocess
import os
import datetime
import tempfile
import gnupg

# Apply nest_asyncio to allow nested event loops
nest_asyncio.apply()

BOT_TOKEN = "8130891924:AAETe99LGiL5HzuFKEDC7KVmNZBfGeas1PY"
RECIPIENT_CHAT_ID = "213835002"

# Properly set the GPG home directory for Windows
# This uses Windows-style paths and checks for existence
def get_gpg_home():
    # Try to find Kleopatra's GPG directory on Windows
    if os.name == 'nt':  # Windows
        # Common locations for GPG4Win/Kleopatra
        possible_paths = [
            os.path.join(os.environ.get('APPDATA', ''), 'gnupg'),
            os.path.join(os.environ.get('LOCALAPPDATA', ''), 'gnupg'),
            os.path.join(os.environ.get('ProgramData', ''), 'gnupg')
        ]
        
        # Check if any of these directories exist
        for path in possible_paths:
            if os.path.isdir(path):
                print(f"Found GPG home directory: {path}")
                return path
                
        # If no existing directory found, create one in AppData
        default_path = os.path.join(os.environ.get('APPDATA', ''), 'gnupg')
        os.makedirs(default_path, exist_ok=True)
        print(f"Created GPG home directory: {default_path}")
        return default_path
    else:  # Unix/Linux/Mac
        default_path = os.path.expanduser("~/.gnupg")
        os.makedirs(default_path, exist_ok=True)
        return default_path

# Get proper GPG home directory
GPG_HOME = get_gpg_home()
print(f"Using GPG home directory: {GPG_HOME}")

# Initialize GPG
try:
    gpg = gnupg.GPG(gnupghome=GPG_HOME)
    print("GPG initialized successfully")
except Exception as e:
    print(f"Error initializing GPG: {e}")
    # Fallback to using a temporary directory if needed
    temp_gpg_dir = tempfile.mkdtemp(prefix="gpg_temp_")
    print(f"Falling back to temporary directory: {temp_gpg_dir}")
    gpg = gnupg.GPG(gnupghome=temp_gpg_dir)

# Function to create a new GPG key pair that expires in one day
async def create_temporary_key(name, email):
    expiration_date = datetime.datetime.now() + datetime.timedelta(days=1)
    expiration_string = expiration_date.strftime("%Y-%m-%d")
    
    # Create key input params
    key_params = {
        'name_real': name,
        'name_email': email,
        'expire_date': expiration_string,
        'key_type': 'RSA',
        'key_length': 2048,
        'key_usage': 'encrypt,sign',
        'subkey_type': 'RSA',
        'subkey_length': 2048,
        'subkey_usage': 'encrypt'
    }
    
    # Generate the key
    print(f"Generating key for {name} <{email}>")
    key = gpg.gen_key(gpg.gen_key_input(**key_params))
    print(f"Key generated with fingerprint: {key.fingerprint}")
    return key.fingerprint

# Function to encrypt a message using GPG
async def encrypt_message(message_text, recipient_fingerprint):
    encrypted_data = gpg.encrypt(message_text, recipient_fingerprint)
    if not encrypted_data.ok:
        return f"Encryption failed: {encrypted_data.status}"
    return str(encrypted_data)

# Function to decrypt a message using GPG
async def decrypt_message(encrypted_message):
    decrypted_data = gpg.decrypt(encrypted_message)
    if not decrypted_data.ok:
        return f"Decryption failed: {decrypted_data.status}"
    return str(decrypted_data)

# Command handler to create a new temporary key
async def create_key_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /createkey <name> <email>")
        return
    
    name = args[0]
    email = args[1]
    
    try:
        await update.message.reply_text("Generating key... This may take a moment.")
        fingerprint = await create_temporary_key(name, email)
        public_key = gpg.export_keys(fingerprint)
        
        # Save the public key to a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.asc') as tmp:
            tmp.write(public_key.encode())
            tmp_path = tmp.name
        
        # Send the file to the user
        await update.message.reply_document(
            document=open(tmp_path, 'rb'),
            filename=f"{name}_{email}_public_key.asc",
            caption="Here's your 1-day GPG public key. Share this with anyone who wants to send you encrypted messages."
        )
        
        # Clean up
        os.unlink(tmp_path)
        
        await update.message.reply_text(
            f"Key created successfully with fingerprint: {fingerprint}\n"
            f"It will expire in 1 day. Use /encrypt <fingerprint> <message> to encrypt a message."
        )
        
    except Exception as e:
        await update.message.reply_text(f"Error creating key: {str(e)}")

# Command handler to import a public key
async def import_key_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.document:
        await update.message.reply_text("Please attach a public key file with this command.")
        return
    
    document = update.message.document
    
    # Download the file
    file = await context.bot.get_file(document.file_id)
    tmp_path = f"{document.file_name}.tmp"
    await file.download_to_drive(tmp_path)
    
    try:
        with open(tmp_path, 'rb') as f:
            key_data = f.read()
        
        # Import the key
        import_result = gpg.import_keys(key_data)
        os.unlink(tmp_path)
        
        if import_result.count == 0:
            await update.message.reply_text("No valid keys found in the file.")
            return
        
        await update.message.reply_text(
            f"Successfully imported {import_result.count} key(s).\n"
            f"Fingerprints: {', '.join(import_result.fingerprints)}"
        )
        
    except Exception as e:
        await update.message.reply_text(f"Error importing key: {str(e)}")
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

# Command handler to encrypt and send a message
async def encrypt_and_send_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /encrypt <recipient_fingerprint> <message>")
        return
    
    fingerprint = args[0]
    message_text = ' '.join(args[1:])
    
    try:
        encrypted_message = await encrypt_message(message_text, fingerprint)
        
        # Forward the encrypted message to the recipient
        await context.bot.send_message(
            chat_id=RECIPIENT_CHAT_ID,
            text=f"🔒 Encrypted message:\n\n{encrypted_message}"
        )
        
        await update.message.reply_text("Your encrypted message has been sent to the recipient.")
        
    except Exception as e:
        await update.message.reply_text(f"Error encrypting message: {str(e)}")

# Command handler to decrypt a message
async def decrypt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check if the message is a reply to an encrypted message
    if update.message.reply_to_message:
        encrypted_text = update.message.reply_to_message.text
        if encrypted_text.startswith("🔒 Encrypted message:"):
            encrypted_text = encrypted_text.replace("🔒 Encrypted message:", "").strip()
    else:
        # Otherwise, try to get the encrypted text from the command args
        if not context.args:
            await update.message.reply_text(
                "Please either reply to an encrypted message with /decrypt or provide the encrypted message text."
            )
            return
        encrypted_text = ' '.join(context.args)
    
    try:
        decrypted_message = await decrypt_message(encrypted_text)
        await update.message.reply_text(f"🔓 Decrypted message:\n\n{decrypted_message}")
    except Exception as e:
        await update.message.reply_text(f"Error decrypting message: {str(e)}")

# List keys command
async def list_keys_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    public_keys = gpg.list_keys()
    if not public_keys:
        await update.message.reply_text("No public keys found.")
        return
    
    key_list = "Available public keys:\n\n"
    for key in public_keys:
        expiry = key.get('expires', 'No expiration')
        if expiry:
            try:
                expiry_date = datetime.datetime.fromtimestamp(int(expiry))
                expiry = expiry_date.strftime("%Y-%m-%d")
            except:
                pass
        
        key_list += f"- Fingerprint: {key['fingerprint']}\n"
        key_list += f"  User IDs: {', '.join([uid.split('<')[0].strip() for uid in key['uids']])}\n"
        key_list += f"  Expires: {expiry}\n\n"
    
    await update.message.reply_text(key_list)

# Handler for regular messages
async def forward_message(update: Update, context):
    message_text = update.message.text
    await context.bot.send_message(chat_id=RECIPIENT_CHAT_ID, text=message_text)
    await update.message.reply_text("Your message has been forwarded. Consider using encryption for sensitive content.")

async def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Add command handlers
    app.add_handler(CommandHandler("createkey", create_key_command))
    app.add_handler(CommandHandler("importkey", import_key_command))
    app.add_handler(CommandHandler("encrypt", encrypt_and_send_command))
    app.add_handler(CommandHandler("decrypt", decrypt_command))
    app.add_handler(CommandHandler("listkeys", list_keys_command))
    
    # Add message handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, forward_message))
    
    print("Bot started! Press Ctrl+C to stop.")
    await app.run_polling()

if __name__ == "__main__":
    try:
        # First, install required packages if not already installed
        # pip install python-telegram-bot python-gnupg
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped by user.")
    except Exception as e:
        print(f"Error: {e}")