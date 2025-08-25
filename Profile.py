users = {}  # user_id: {name, age, gender, interest, respect}

def create_profile(user_id, name, age, gender):
    users[user_id] = {
        "name": name,
        "age": age,
        "gender": gender,
        "interest": None,
        "respect": 100,
        "chat_partner": None,
    }
    return users[user_id]

def set_interest(user_id, interest):
    if user_id in users:
        users[user_id]["interest"] = interest
