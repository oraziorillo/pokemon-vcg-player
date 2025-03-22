import gradio as gr
from poke_env import Player, ShowdownServerConfiguration, AccountConfiguration


account_config = AccountConfiguration("vehlgavekcghvea", "super-secret-password")
player = Player(server_configuration=ShowdownServerConfiguration, account_configuration=account_config)


def greet(name):
    return f"Hello, {name}!"

# iframe code to embed Pokemon Showdown
iframe_code = """
<iframe
    src="https://pshowdown-test-client.hf.space"
    width="100%"
    height="800"
    style="border: none;"
>
</iframe>
"""

def main():
    with gr.Blocks() as demo:
        gr.Markdown("# Simple Python + Pokémon Showdown Demo")

        name_input = gr.Textbox(label="Enter your name here")
        greet_button = gr.Button("Play")

        greet_button.click(fn=greet, inputs=name_input)
        
        gr.Markdown("### Pokémon Showdown Iframe")
        gr.HTML(iframe_code)

    return demo

if __name__ == "__main__":
    demo = main()
    demo.launch()
