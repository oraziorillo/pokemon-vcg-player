import gradio as gr

# A simple Python function to demonstrate code execution
def greet(name):
    return f"Hello, {name}!"

# iframe code to embed Pokemon Showdown
# (Note: If the site blocks embedding, the iframe might not display)
iframe_code = """
<iframe
    src="https://play.pokemonshowdown.com/"
    width="100%"
    height="800"
    style="border: none;"
>
</iframe>
"""

def main():
    with gr.Blocks() as demo:
        gr.Markdown("# Simple Python + Pokémon Showdown Demo")

        # --- Simple Python function UI ---
        with gr.Box():
            gr.Markdown("### Simple Greeting Function")
            name_input = gr.Textbox(label="Enter your name here")
            greet_button = gr.Button("Greet")
            greet_output = gr.Textbox(label="Output")

            greet_button.click(fn=greet, inputs=name_input, outputs=greet_output)
        
        gr.Markdown("### Pokémon Showdown Iframe")
        gr.HTML(iframe_code)

    return demo

if __name__ == "__main__":
    demo = main()
    demo.launch()
