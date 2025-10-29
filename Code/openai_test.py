from openai import OpenAI
client = OpenAI()
resp = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Say hello in one short sentence."}
    ],
    max_tokens=20,
)
print("MODEL:", resp.model)
print("TOKENS:", resp.usage.prompt_tokens, "+", resp.usage.completion_tokens, "=", resp.usage.total_tokens)
print(resp.choices[0].message.content)