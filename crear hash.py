import bcrypt

password = ""

hash_password = bcrypt.hashpw(
    password.encode("utf-8"),
    bcrypt.gensalt()
)

print(hash_password.decode("utf-8"))
print(hash_password.decode("utf-8"))