import gradio as gr

def greet(name):
    return f"Hello, {name}!"

# iframe code to embed Pokemon Showdown
iframe_code = """
<iframe
    src="https://pokemonshowdown.com/"
    width="100%"
    height="800"
    style="border: none;"
>
</iframe>
"""

def main():
    with gr.Blocks() as demo:
        gr.Markdown("# Simple Python + Pokémon Showdown Demo")

        gr.Markdown("### Simple Greeting Function")
        name_input = gr.Textbox(label="Enter your name here")
        greet_button = gr.Button("Play")

        greet_button.click(fn=greet, inputs=name_input)
        
        gr.Markdown("### Pokémon Showdown Iframe")
        gr.HTML(iframe_code)

    return demo

if __name__ == "__main__":
    demo = main()
    demo.launch()
