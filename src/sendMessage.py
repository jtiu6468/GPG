from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
import asyncio
import nest_asyncio
import subprocess
import os
import datetime
import tempfile
import gnupg

# Nested event loops
nest_asyncio.apply()

BOT_TOKEN = "8130891924:AAETe99LGiL5HzuFKEDC7KVmNZBfGeas1PY"
RECIPIENT_CHAT_ID = "1668013863"
#HosRo: 213835002
#Jaine: 1668013863

# Checks if GPG is installed on the system
def get_gpg_home():
    if os.name == 'nt': 
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
        with tempfile.NamedTemporaryFile(delete=False, suffix='.txt') as tmp:
            tmp.write(public_key.encode())
            tmp_path = tmp.name
        
        # Ensure the file is closed before sending it to the user
        with open(tmp_path, 'rb') as file:
            await update.message.reply_document(
                document=file,
                filename=f"{name}_{email}_public_key.txt",
                caption="Here's your 1-day GPG public key. Share this with anyone who wants to send you encrypted messages."
            )
        
        # Clean up the temporary file
        os.unlink(tmp_path)
        
        await update.message.reply_text(
            f"Key created successfully with fingerprint: `{fingerprint}`\n"
            f"\nFingerprint will expire in 1 day. Use /encrypt <fingerprint> <message> to encrypt a message.",
            parse_mode='Markdown'
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


# Encrypt and send a message
async def encrypt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            text=f"Encrypted message:\n\n{encrypted_message}"
        )  
        await update.message.reply_text("Your encrypted message has been sent.")
        
    except Exception as e:
        await update.message.reply_text(f"Error encrypting message: {str(e)}")


# Decrypt a message
async def decrypt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Get the encrypted text from a reply or command arguments
    if update.message.reply_to_message:
        encrypted_text = update.message.reply_to_message.text
        if encrypted_text.startswith("Encrypted message:"):
            encrypted_text = encrypted_text.replace("Encrypted message:", "").strip()
    else:
        if not context.args:
            await update.message.reply_text(
                "Please reply to an encrypted message with /decrypt or provide the encrypted message."
            )
            return
        encrypted_text = ' '.join(context.args)

    try:
        decrypted_data = gpg.decrypt(encrypted_text)
        if not decrypted_data.ok:
            await update.message.reply_text(f"Decryption failed: {decrypted_data.status}")
            return

        # Safely decode decrypted output
        try:
            decrypted_text = str(decrypted_data)
        except UnicodeDecodeError:
            decrypted_text = decrypted_data.data.decode('utf-8', errors='replace')

        await update.message.reply_text(f"Decrypted message:\n\n{decrypted_text}")
    except Exception as e:
        await update.message.reply_text(f"Error decrypting message: {str(e)}")

        

# Help command to list all available commands
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "Available Commands:\n\n"
        "/createkey <name> <email> - Generate public key\n"
        "/encrypt <fingerprint> <message> – Encrypt and send a message\n"
        "/decrypt – Decrypt a message (reply to an encrypted one or pass it as argument)\n"
        "/importkey – Attach and import a public key\n"
        "/listkeys – List available public keys\n"
        # Add more commands if you have them
    )
    await update.message.reply_text(help_text)

        


# List and delete expired keys command
async def list_keys_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Lists all public keys "/listkeys"
    public_keys = gpg.list_keys()
    
    if not public_keys:
        await update.message.reply_text("No public keys found.")
        return
    
    key_list = "Available public keys:\n\n"
    deleted_keys = [] 
    
    # Iterate through each key found in the public keys list
    for key in public_keys:
        # Extract the expiration date (if available)
        expiry = key.get('expires', 'No expiration')
        expiry_date = None
        
        if expiry and expiry != 'No expiration':
            try:
                expiry_date = datetime.datetime.fromtimestamp(int(expiry))
            except:
                expiry_date = None

        # If the key has expired, delete it
        if expiry_date and expiry_date < datetime.datetime.now():
            try:
                # Delete the expired key
                gpg.delete_keys(key['fingerprint'])
                deleted_keys.append(key['fingerprint'])
                continue  # Skip adding this key to the list
            except Exception as e:
                await update.message.reply_text(f"Error deleting key {key['fingerprint']}: {str(e)}")
                continue
        
        # If not expired, add the key details to the list
         #f"Key created successfully with fingerprint: `{fingerprint}`\n"
        key_list += f"  Fingerprint: {key['fingerprint']}\n"
        key_list += f"  User IDs: {', '.join([uid.split('<')[0].strip() for uid in key['uids']])}\n"
        key_list += f"  Expires: {expiry_date.strftime('%Y-%m-%d') if expiry_date else 'No expiration'}\n\n"
        parse_mode='Markdown'

    # If no valid keys remain, notify the user
    if key_list == "Available public keys:\n\n":
        await update.message.reply_text("No valid public keys available.")
    else:
        await update.message.reply_text(key_list)



# Forwards regular (non-encrypted) messages
async def forward_message(update: Update, context):
    message_text = update.message.text
    await context.bot.send_message(chat_id=RECIPIENT_CHAT_ID, text=message_text)
    await update.message.reply_text("Your message has been forwarded. Consider using encryption for sensitive content.")



async def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    # List of telegram commands available
    app.add_handler(CommandHandler("createkey", create_key_command))
    app.add_handler(CommandHandler("importkey", import_key_command))
    app.add_handler(CommandHandler("encrypt", encrypt_command))
    app.add_handler(CommandHandler("decrypt", decrypt_command))
    app.add_handler(CommandHandler("listkeys", list_keys_command))
    app.add_handler(CommandHandler("help", help_command))
    
    # If message sent is not a command will send as a regular message (not encrypted)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, forward_message))
    
    print("Bot started! Press Ctrl+C to stop.")
    await app.run_polling()

if __name__ == "__main__":
    try:
        # start an event loop and run the asynchronous main() function until it's complete
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped by user.")
    except Exception as e:
        print(f"Error: {e}")
