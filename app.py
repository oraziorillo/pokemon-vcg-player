# app.py
import gradio as gr
import asyncio
import threading
import os

# Import poke-env components
from poke_env.player import Player, RandomPlayer
from poke_env import AccountConfiguration,ServerConfiguration
# Import your custom agent
from agents import OpenAIAgent


# --- Global variables for players and thread ---
random_player: Player | None = None
openai_agent: Player | None = None
agent_init_thread: threading.Thread | None = None
init_lock = threading.Lock() # To prevent race conditions during init
agents_initialized = False

# --- Configuration ---
custom_config = ServerConfiguration(
     "wss://jofthomas.com/showdown/websocket", # WebSocket URL
     "https://jofthomas.com/showdown/action.php" # Authentication URL
)


DEFAULT_BATTLE_FORMAT = "gen9randombattle"

# --- Agent Initialization ---
def initialize_agents_sync():
    """Initializes both player agents in a background thread."""
    global random_player, openai_agent, agents_initialized
    # Ensure this runs only once
    with init_lock:
        if agents_initialized:
            print("Agents already initialized.")
            return
        print("Initializing agents...")
        # We need an event loop in this new thread for player initialization
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            
            random_player = RandomPlayer(
                server_configuration=custom_config,
                battle_format=DEFAULT_BATTLE_FORMAT
            )
            print("RandomPlayer initialized.")

            # Initialize OpenAI Agent

            openai_agent = OpenAIAgent(
                server_configuration=custom_config,
                battle_format=DEFAULT_BATTLE_FORMAT
            )
            print("OpenAIAgent initialized.")

            agents_initialized = True
            print("Agent initialization complete.")
        except Exception as e:
            print(f"!!! Error during agent initialization: {e}")
            # Reset globals if init fails partially
            random_player = None
            openai_agent = None
            agents_initialized = False
        # Note: Don't close the loop here, the players might need it running implicitly
        # loop.close()

# Function to start the initialization thread
def start_agent_initialization():
    """Starts the agent initialization thread if not already running."""
    global agent_init_thread
    if not agents_initialized and (agent_init_thread is None or not agent_init_thread.is_alive()):
        print("Starting agent initialization thread...")
        agent_init_thread = threading.Thread(target=initialize_agents_sync, daemon=True)
        agent_init_thread.start()
    elif agents_initialized:
        print("Agents already initialized, no need to start thread.")
    else:
        print("Initialization thread already running.")

# --- Battle Invitation Logic ---
async def send_battle_invite_async(player: Player, username: str, battle_format: str = DEFAULT_BATTLE_FORMAT):
    """Sends a challenge using the provided player object."""
    if player is None:
        return "Error: The selected player is not available/initialized."
    if not username or not username.strip():
         return "Error: Please enter a valid Showdown username."
    try:
        print(f"Attempting to send challenge from {player.username} to {username} in format {battle_format}")
        print(player)
        # Using send_challenges which should handle login implicitly if needed
        await player.send_challenges(username, n_challenges=1)
        return f"Battle invitation ({battle_format}) sent to {username} from bot {player.username}! Check Showdown."
    except Exception as e:
        # Log the full error for debugging
        import traceback
        print(f"Error sending challenge from {player.username}:")
        traceback.print_exc() # Print stack trace
        return f"Error sending challenge: {str(e)}. Check console logs."

# Wrapper for the async function to use in Gradio, handling agent selection
def invite_to_battle(agent_choice: str, username: str):
    """Selects the agent and initiates the battle invitation."""
    global random_player, openai_agent, agents_initialized

    if not agents_initialized:
         # Try to initialize if the button is clicked before init finishes
         start_agent_initialization()
         return "Agents are initializing, please wait a few seconds and try again."

    selected_player: Player | None = None
    if agent_choice == "Random Player":
        selected_player = random_player
        if selected_player is None:
            return "Error: Random Player is not available. Initialization might have failed."
    elif agent_choice == "OpenAI Agent":
        selected_player = openai_agent
        if selected_player is None:
            # Check if API key might be the issue
            if not os.getenv("OPENAI_API_KEY"):
                 return "Error: OpenAI Agent not available. OPENAI_API_KEY is missing."
            else:
                 return "Error: OpenAI Agent not available. Initialization might have failed. Check logs."
    else:
        return "Error: Invalid agent choice selected."

    # Ensure username is provided
    username_clean = username.strip()
    if not username_clean:
        return "Please enter your Showdown username."

    # Run the async challenge function in a managed event loop
    try:
        # Try to get the existing loop from the init thread or create a new one
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
             print("No running event loop, creating new one for challenge.")
             loop = asyncio.new_event_loop()
             asyncio.set_event_loop(loop)

        # If the main loop is running, schedule the task; otherwise, run until complete
        if loop.is_running():
            # Schedule the coroutine and wait for its result
            future = asyncio.run_coroutine_threadsafe(
                send_battle_invite_async(selected_player, username_clean), loop
            )
            result = future.result(timeout=30) # Add a timeout
        else:
             result = loop.run_until_complete(
                 send_battle_invite_async(selected_player, username_clean)
             )

        return result
    except TimeoutError:
        return "Error: Sending challenge timed out."
    except Exception as e:
        print(f"Unexpected error in invite_to_battle's async execution: {e}")
        import traceback
        traceback.print_exc()
        return f"An unexpected error occurred: {e}"


# --- Gradio UI Definition ---
# iframe code to embed Pokemon Showdown (using official URL)
iframe_code = """
<iframe
    src="https://jofthomas.com/play.pokemonshowdown.com/testclient.html"
    width="100%"
    height="800"
    style="border: none;"
    referrerpolicy="no-referrer">
</iframe>
"""

def main_app():
    """Creates and returns the Gradio application interface."""
    # Start agent initialization when the app is defined/loaded
    start_agent_initialization()

    # Using gr.Blocks. The default layout should stretch reasonably wide.
    with gr.Blocks(title="Pokemon Showdown Bot") as demo:
        gr.Markdown("# Pokémon Showdown Battle Bot")
        gr.Markdown(
            "Select a bot agent, enter **your** Showdown username "
            "(the one you are logged in with below), and click Send Invite."
        )

        # --- Row for Controls at the Top ---
        with gr.Row():
            # Place controls here
            agent_dropdown = gr.Dropdown(
                label="Select Bot Agent",
                choices=["Random Player", "OpenAI Agent"],
                value="Random Player",
                scale=1 # Give dropdown reasonable space
            )
            name_input = gr.Textbox(
                label="Your Pokémon Showdown Username",
                placeholder="Enter username used in Showdown below",
                scale=2 # Give name input more relative space
            )
            battle_button = gr.Button("Send Battle Invitation", scale=1) # Button takes less space
            status_output = gr.Textbox(
                label="Status",
                interactive=False,
                lines=1, # Keep status compact initially
                scale=2 # Give status reasonable space
            )

        # --- Section for the IFrame below the controls ---
        gr.Markdown("### Pokémon Showdown Interface")
        gr.Markdown("Log in/use the username you entered above.")
        # The HTML component containing the iframe will take up the available width
        gr.HTML(iframe_code)

        # --- Connect button click to the invitation function ---
        battle_button.click(
            fn=invite_to_battle,
            inputs=[agent_dropdown, name_input],
            outputs=status_output # Display result/status here
        )

    return demo

# --- Main execution block ---
if __name__ == "__main__":
    # Create and launch the Gradio app
    app = main_app()
    # You might need to configure server_name and server_port depending on your deployment environment
    # Use app.launch(share=True) for a public link (if needed and safe)
    app.launch() # server_name="0.0.0.0" # To make accessible on network