from telegram import Update, Message
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes, ConversationHandler
import asyncio, nest_asyncio, subprocess, os, datetime, tempfile, gnupg, re

nest_asyncio.apply()
PASSPHRASE = 0
BOT_TOKEN = "8130891924:AAETe99LGiL5HzuFKEDC7KVmNZBfGeas1PY"
RECIPIENT_CHAT_ID = "REPLACE WITH RECIPIENT CHAT ID"



# Locate directory of GPG (install it in APPDATA)
def get_gpg_home():
    path = os.path.join(os.environ.get('APPDATA', ''), 'gnupg')
    os.makedirs(path, exist_ok=True)
    return path

GPG_HOME = get_gpg_home()

try:
    gpg = gnupg.GPG(gnupghome=GPG_HOME)
    print("GPG initialized successfully.")
except Exception as e:
    f"GPG setup failed ({e}).\nCreating a temporary GPG home."
    gpg = gnupg.GPG(gnupghome=tempfile.mkdtemp(prefix="temp_gpg_"))



# Generates a temporary GPG key for encryption and signing which will expire in 1 day
async def create_temp_key(name, email, passphrase):
    key_params = {
        'name_real': name,
        'name_email': email,
        'key_type': 'RSA',
        'key_length': 2048,
        'key_usage': 'encrypt,sign',
        'subkey_type': 'RSA',
        'subkey_length': 2048,
        'subkey_usage': 'encrypt,sign',
        'passphrase': passphrase,
        'expire_date': '1d'
    }
    key = gpg.gen_key(gpg.gen_key_input(**key_params))
    fingerprint = key.fingerprint
    expires = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime('%m-%d-%Y %H:%M:%S')
    
    return fingerprint, expires



# Encrypts a message using GPG for a recipient
async def encrypt_message(message, recipient_fingerprint):
    encrypted_data = gpg.encrypt(message, recipient_fingerprint)
    if not encrypted_data.ok:
        return f"Encryption failed: {encrypted_data.status}"
    return str(encrypted_data)



# Decrypt an encrypted message using GPG
async def decrypt_message(encrypted_message):
    decrypted_data = gpg.decrypt(encrypted_message)
    if not decrypted_data.ok:
        return f"Decryption failed: {decrypted_data.status}"
    return str(decrypted_data)



# Prompts the user to enter a passphrase for a GPG key
async def create_key_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    context.user_data['name'] = args[0]
    context.user_data['email'] = args[1]
    if len(args) < 2:
        await update.message.reply_text("Usage: /createkey <name> <email>")
        return ConversationHandler.END

    await update.message.reply_text("Please enter a passphrase with at least 12 characters and at least one symbol (ex: mypassword@123).")
    return PASSPHRASE



# Validates the user's passphrase, generates a GPG key, and sends the public key and fingerprint to the user
async def get_passphrase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    passphrase = update.message.text
    name = context.user_data.get('name')
    email = context.user_data.get('email')

    if len(passphrase) < 12 or not re.search(r'[\W_]', passphrase):
        try:
            await update.message.delete()
        except Exception as e:
            await update.message.reply_text("Consider deleting failed passphrase manually for security.")
        await update.message.reply_text("Invalid passphrase. Please enter a new one, ensure it has at least 12 characters and contains at least one symbol.")
        return PASSPHRASE

    try:
        await update.message.delete()
    except Exception as e:
        await update.message.reply_text("Consider deleting passphrase manually for security.")

    if 'waiting_for_passphrase' in context.user_data:
        encrypted_text = context.user_data.pop('waiting_for_passphrase')
        decrypted_data = gpg.decrypt(encrypted_text, passphrase=passphrase)

        if not decrypted_data.ok:
            await update.message.reply_text(f"Decryption failed: {decrypted_data.status}")
            return ConversationHandler.END

        decrypted_text = str(decrypted_data) 
        await update.message.reply_text(f"Decrypted message:\n\n{decrypted_text}")
        
        context.user_data.clear()
        return ConversationHandler.END

    if 'name' not in context.user_data or 'email' not in context.user_data:
        await update.message.reply_text("Error: Missing name or email. Please retry /createkey.")
        return ConversationHandler.END

    await update.message.reply_text(f"Valid passphrase received for {name}, {email}. Generating your fingerprint...")

    try:
        fingerprint, expires = await create_temp_key(name, email, passphrase)
        public_key = gpg.export_keys(fingerprint)

        with tempfile.NamedTemporaryFile(delete=False, suffix='.txt') as tmp:
            tmp.write(public_key.encode())
            tmp_path = tmp.name
        
        with open(tmp_path, 'rb') as file:
            await update.message.reply_document(
                document=file,
                filename=f"{name}_{email}_public_key.txt",
                caption="Here's your 1-day GPG public key. Share this with anyone who wants to send you encrypted messages."
            )
        
        os.unlink(tmp_path)
        
        await update.message.reply_text(
            f"Key created successfully with fingerprint: `{fingerprint}`.\n"
            f"\nKey will expire in 1 day ({expires}).\nUse /encrypt <fingerprint> <message> to encrypt a message.",
            parse_mode='Markdown'
        )

    except Exception as e:
        await update.message.reply_text(f"Error creating key: {str(e)}")

    context.user_data.clear()
    return ConversationHandler.END



# Imports a public key and validates it
async def import_key_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    
    if not update.message.document:
        await update.message.reply_text("Please attach a public key file with this command.")
        return
    
    file = await context.bot.get_file(document.file_id)
    tmp_path = f"{document.file_name}.tmp"
    await file.download_to_drive(tmp_path)
    
    try:
        with open(tmp_path, 'rb') as f:
            key_data = f.read()
    
        import_result = gpg.import_keys(key_data)
        os.unlink(tmp_path)
  
        if import_result.count == 0:
            await update.message.reply_text("No valid keys found in the file.")
            return
        
        await update.message.reply_text(
            f"Successfully imported: {import_result.count}.\n"
            f"Fingerprints: {', '.join(import_result.fingerprints)}"
        )
        
    except Exception as e:
        await update.message.reply_text(f"Error importing key: {str(e)}")
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)



# Encrypts a message using the recipient's fingerprint and sends the encrypted message to the recipients chat
async def encrypt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /encrypt <recipient_fingerprint> <message>")
        return
    try:
        await update.message.delete()
    except Exception as e:
        print(f"Could not delete passphrase message: {e}")
        
    fingerprint = args[0]
    message = ' '.join(args[1:])
    
    try:
        encrypted_message = await encrypt_message(message, fingerprint)     

        await context.bot.send_message(
            chat_id=RECIPIENT_CHAT_ID,
            text=f"Encrypted message:\n\n{encrypted_message}"
        )  
        await update.message.reply_text("Your encrypted message has been sent.")
        
    except Exception as e:
        await update.message.reply_text(f"Error encrypting message: {str(e)}")



# Decrypts an encrypted message and sends the decrypted message back to the user
async def decrypt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    passphrase = args[0]
    
    if len(args) < 1:
        await update.message.reply_text("Usage: /decrypt <passphrase>")
        return

    try:
        await update.message.delete()
    except Exception as e:
        print(f"Could not delete passphrase message: {e}")

    if update.message.reply_to_message:
        encrypted_text = update.message.reply_to_message.text
        if encrypted_text.startswith("Encrypted message:"):
            encrypted_text = encrypted_text.replace("Encrypted message:", "").strip()
    else:
        await update.message.reply_text("Please reply to an encrypted message with /decrypt <passphrase>.")
        return
    
    decrypted_data = gpg.decrypt(encrypted_text, passphrase=passphrase)

    if not decrypted_data.ok:
        await update.message.reply_text(f"Decryption failed: {decrypted_data.status}")
        return

    decrypted_text = str(decrypted_data)
    await update.message.reply_text(f"Decrypted message:\n\n{decrypted_text}")



# Sends a message with the available commands and their usage
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "Available Commands:\n\n"
        "/createkey <name> <email> - Generate public key\n"
        "/encrypt <fingerprint> <message> – Encrypt and send a message\n"
        "/decrypt <passphrase> – Decrypt a message (reply to an encrypted message or pass it as argument)\n"
        "/importkey – Attach and import a public key\n"
        "/listkeys – List available public keys\n"
    )
    await update.message.reply_text(help_text)

        
        
# Lists and deletes expired public keys 
async def list_keys_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    public_keys = gpg.list_keys()
    key_list = "Available public keys:\n\n"
    deleted_keys = [] 
    
    if not public_keys:
        await update.message.reply_text("No public keys found.")
        return
    
    for key in public_keys:
        expiry = key.get('expires', 'No expiration date set')
        expiry_date = None
        
        if expiry and expiry != 'No expiration date set':
            try:
                expiry_date = datetime.datetime.fromtimestamp(int(expiry))
            except:
                expiry_date = None

        if expiry_date and expiry_date < datetime.datetime.now():
            try:
                gpg.delete_keys(key['fingerprint'])
                deleted_keys.append(key['fingerprint'])
                continue  
            except Exception as e:
                await update.message.reply_text(f"Error deleting key {key['fingerprint']}: {str(e)}")
                continue
        
        key_list += f"  Fingerprint: `{key['fingerprint']}`\n"
        key_list += f"  User ID: {', '.join([uid.split('<')[0].strip() for uid in key['uids']])}\n"
        key_list += f"  Expires: {expiry_date.strftime('%m-%d-%Y %H:%M:%S') if expiry_date else 'No expiration'}\n\n"

    if key_list == "Available public keys:\n\n":
        await update.message.reply_text("No valid public keys available.")
    else:
        await update.message.reply_text(key_list,  parse_mode='Markdown')



# Sends a non-encrypted message to recipeinet if user doesn't use /encrypt
async def forward_message(update: Update, context):
    message = update.message.text
    await context.bot.send_message(chat_id=RECIPIENT_CHAT_ID, text=message)
    await update.message.reply_text("Your message has been forwarded. Consider using /encrypt for better security.")



async def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("createkey", create_key_command)],
        states={
            PASSPHRASE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_passphrase)]
        },
        fallbacks=[],
        allow_reentry=True,
        name="key_creation_convo"
    )
    
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("encrypt", encrypt_command))
    app.add_handler(CommandHandler("decrypt", decrypt_command))
    app.add_handler(CommandHandler("importkey", import_key_command))
    app.add_handler(CommandHandler("listkeys", list_keys_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, forward_message))

    print("JK-GPG-Bot started! Press Ctrl+C to stop.")
    await app.run_polling()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("JK-GPG-Bot stopped by user.")
    except Exception as e:
        print(f"Error: {e}")
