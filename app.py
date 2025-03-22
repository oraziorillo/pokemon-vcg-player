import gradio as gr
from poke_env.player.random_player import RandomPlayer
from poke_env import AccountConfiguration, ShowdownServerConfiguration
import asyncio
import threading

# Set up the random player
server_config = ShowdownServerConfiguration()
random_player = None
player_thread = None

# Function to start the random player in a separate thread
def start_random_player():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    global random_player
    
    random_player = RandomPlayer(
        player_configuration=AccountConfiguration("huggingface_random", None)
        server_configuration=ShowdownServerConfiguration,
    )
    
    # Start the player
    loop.run_until_complete(random_player.accept_challenges(max_concurrent_battles=1))

# Start the random player in a background thread
def initialize_random_player():
    global player_thread
    player_thread = threading.Thread(target=start_random_player)
    player_thread.daemon = True
    player_thread.start()

# Function to send a battle invite
async def send_battle_invite(username):
    if random_player is None:
        return f"Error: Random player not initialized. Try again."
    
    try:
        # Send a challenge to the user
        await random_player.send_challenges(username, n_challenges=1)
        return f"Battle invitation sent to {username}! Check the Pokemon Showdown interface below."
    except Exception as e:
        return f"Error sending challenge: {str(e)}"

# Wrapper for the async function to use in Gradio
def invite_to_battle(username):
    if not username.strip():
        return "Please enter a valid username."
    
    loop = asyncio.new_event_loop()
    result = loop.run_until_complete(send_battle_invite(username))
    loop.close()
    return result

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
    # Initialize the random player when the app starts
    initialize_random_player()
    
    with gr.Blocks() as demo:
        gr.Markdown("# Pokémon Showdown Battle Bot")
        
        with gr.Row():
            with gr.Column():
                gr.Markdown("### Enter your Pokémon Showdown username to receive a battle invitation:")
                name_input = gr.Textbox(label="Your Pokémon Showdown Username", placeholder="Enter the username you're using on Showdown")
                battle_button = gr.Button("Send Battle Invitation")
                result_text = gr.Textbox(label="Result", interactive=False)
                
                battle_button.click(fn=invite_to_battle, inputs=name_input, outputs=result_text)
        
        gr.Markdown("### Pokémon Showdown Interface")
        gr.Markdown("Log in to Pokémon Showdown in the interface below, using the same username you entered above.")
        gr.HTML(iframe_code)

    return demo

if __name__ == "__main__":
    demo = main()
    demo.launch()
