from rapidfuzz import process

# GENDER_VALUES = ["male", "female"]

# def correct_gender(user_input):
#     match, score, _ = process.extractOne(
#         user_input.lower(),
#         GENDER_VALUES
#     )
#     if score >= 50:
#         return match

#     return None


def correct_word(word):
    choices = ["male", "female"]

    match, score, _ = process.extractOne(
        word.lower(),
        choices
    )

    if score > 80:
        return match

    return word

query = "is there any femsle available in B positive blood group"

words = query.split()

corrected = [correct_word(w) for w in words]

print(" ".join(corrected))