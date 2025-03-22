import gradio as gr
from playwright.sync_api import sync_playwright
import time


#account_config = AccountConfiguration("vehlgavekcghvea", "super-secret-password")
#player = Player(server_configuration=ShowdownServerConfiguration, account_configuration=account_config)


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

def interact_with_showdown(username):
    """Function to interact with Pokemon Showdown iframe using Playwright"""
    with sync_playwright() as p:
        # Launch a browser
        browser = p.chromium.launch(headless=False)  # Set headless=True in production
        page = browser.new_page()
        
        # Navigate to the Pokemon Showdown page directly
        page.goto("https://pshowdown-test-client.hf.space")
        
        # Wait for the page to load
        page.wait_for_load_state("networkidle")
        
        # Enter username - adjust the selectors based on the actual iframe content
        try:
            # Wait for the username input to be available
            page.wait_for_selector("input[name='username']", timeout=5000)
            page.fill("input[name='username']", username)
            
            # Click the choose name button
            page.click("button:has-text('Choose Name')")
            
            # Wait a moment to see the result
            time.sleep(2)
            
            result = f"Successfully set username to {username}"
        except Exception as e:
            result = f"Failed to interact with Pokemon Showdown: {str(e)}"
        finally:
            # Take a screenshot for debugging
            page.screenshot(path="showdown_interaction.png")
            browser.close()
            
        return result

def main():
    with gr.Blocks() as demo:
        gr.Markdown("# Simple Python + Pokémon Showdown Demo")

        name_input = gr.Textbox(label="Enter your username")
        interact_button = gr.Button("Set Username in Showdown")
        result_text = gr.Textbox(label="Result")

        # Connect the interaction function
        interact_button.click(fn=interact_with_showdown, 
                              inputs=name_input, 
                              outputs=result_text)
        
        gr.Markdown("### Pokémon Showdown Iframe")
        gr.HTML(iframe_code)

    return demo

if __name__ == "__main__":
    demo = main()
    demo.launch()
