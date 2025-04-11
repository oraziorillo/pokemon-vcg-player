import gradio as gr
import asyncio
import threading
import os
import random
import traceback
from queue import Queue # For communication if needed, though run_coroutine_threadsafe handles results

from poke_env.player import Player, RandomPlayer
from poke_env import AccountConfiguration, ServerConfiguration
from agents import OpenAIAgent # Assuming this exists

# --- Global variables ---
random_player: Player | None = None
openai_agent: Player | None = None
poke_env_loop: asyncio.AbstractEventLoop | None = None # Store the dedicated loop
poke_env_thread: threading.Thread | None = None
agents_initialized = False
init_lock = threading.Lock() # Keep the lock for initialization logic

# --- Configuration ---
custom_config = ServerConfiguration(
    "wss://jofthomas.com/showdown/websocket",
    "https://jofthomas.com/showdown/action.php"
)
RANDOM_PLAYER_BASE_NAME = "RandomAgent"
OPENAI_AGENT_BASE_NAME = "OpenAIAgent" # Note: Your code uses "MistralAgent" for OpenAI config
DEFAULT_BATTLE_FORMAT = "gen9randombattle"

# --- Background Thread and Loop Management ---

def run_poke_env_loop():
    """Target function for the background thread. Runs the asyncio loop."""
    global poke_env_loop
    try:
        print("Starting dedicated poke-env event loop...")
        poke_env_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(poke_env_loop)
        # Keep the loop running indefinitely
        poke_env_loop.run_forever()
    except Exception as e:
        print(f"!!! Error in poke-env background loop: {e}")
        traceback.print_exc()
    finally:
        if poke_env_loop and poke_env_loop.is_running():
            poke_env_loop.stop() # Gracefully stop if possible
            # Consider loop.close() after stopping if resources need explicit release
        print("Poke-env event loop stopped.")
        poke_env_loop = None # Clear the loop variable


async def initialize_agents_async():
    """Coroutine to initialize agents within the dedicated loop."""
    global random_player, openai_agent, agents_initialized
    # Generate random suffixes
    random_player_suffix = random.randint(1000, 999999)
    # openai_agent_suffix = random.randint(1000, 999999) # Not used in current config

    random_player_username = f"{RANDOM_PLAYER_BASE_NAME}{random_player_suffix}"
    # Your code uses a fixed name and password from env var for the second agent
    openai_agent_username = "MistralAgent" # Or use OPENAI_AGENT_BASE_NAME + suffix if intended

    random_account_config = AccountConfiguration(random_player_username, None)
    openai_password = os.environ.get('SHOWDOWN_PSWD')
    if not openai_password:
         print("!!! WARNING: SHOWDOWN_PSWD environment variable not set for OpenAI agent.")
         # Decide how to handle this - maybe prevent OpenAI agent init?
         # For now, we'll let it potentially fail during init below.
    openai_account_config = AccountConfiguration(openai_agent_username, openai_password)

    print(f"Using RandomPlayer username: {random_account_config.username}")
    print(f"Using OpenAIAgent username: {openai_account_config.username}")

    with init_lock:
        if agents_initialized:
            print("Agents already initialized.")
            return
        print("Initializing agents...")
        try:
            print(f"Initializing RandomPlayer ({random_account_config.username})...")
            random_player = RandomPlayer(
                account_configuration=random_account_config,
                server_configuration=custom_config,
                battle_format=DEFAULT_BATTLE_FORMAT,
                # Explicitly provide the loop if poke-env supports it, otherwise it uses asyncio.get_event_loop()
                # loop=poke_env_loop # Check poke-env docs if 'loop' parameter is accepted
            )
            print("RandomPlayer initialized.")

            print(f"Initializing OpenAIAgent ({openai_account_config.username})...")
            openai_agent = OpenAIAgent(
                account_configuration=openai_account_config,
                server_configuration=custom_config,
                battle_format=DEFAULT_BATTLE_FORMAT,
                # loop=poke_env_loop # Check poke-env docs if 'loop' parameter is accepted
            )
            # Add a small delay or check for connection status if needed
            # await asyncio.sleep(2) # Example: Allow time for connection
            # Add checks like: if random_player.logged_in and openai_agent.logged_in:
            print("OpenAIAgent initialized.")
            agents_initialized = True
            print("Agent initialization complete.")
            # else: raise RuntimeError("One or more agents failed to log in.")

        except Exception as e:
            print(f"!!! Error during agent initialization: {e}")
            traceback.print_exc()
            # Reset globals if init fails partially
            if isinstance(random_player, Player): random_player.close() # Attempt cleanup if possible
            if isinstance(openai_agent, Player): openai_agent.close()
            random_player = None
            openai_agent = None
            agents_initialized = False


def start_poke_env_thread():
    """Starts the background thread for the poke-env event loop and agent initialization."""
    global poke_env_thread, poke_env_loop
    if poke_env_thread is None or not poke_env_thread.is_alive():
        print("Starting poke-env background thread and loop...")
        poke_env_thread = threading.Thread(target=run_poke_env_loop, daemon=True)
        poke_env_thread.start()

        # Wait briefly for the loop to start before scheduling init
        # A more robust way would use threading.Event or Queue
        import time
        time.sleep(1)

        if poke_env_loop:
            print("Scheduling agent initialization...")
            # Schedule the async initialization function to run on the background loop
            future = asyncio.run_coroutine_threadsafe(initialize_agents_async(), poke_env_loop)
            # Optionally wait for init to finish or handle errors
            try:
                future.result(timeout=60) # Wait for initialization up to 60 seconds
                print("Agent initialization scheduled and completed.")
            except Exception as e:
                print(f"!!! Agent initialization failed: {e}")
                # Handle the case where init itself failed
                # The background loop thread will still be running unless it crashed.
        else:
             print("!!! Error: poke-env loop did not start correctly.")

    elif agents_initialized:
        print("Agents already initialized.")
    else:
        print("Poke-env thread already running (initialization might be in progress or failed).")


# --- Battle Invitation Logic (Revised) ---

# Keep the async function as is, but improve logging slightly
async def send_battle_invite_async(player: Player, username: str, battle_format: str = DEFAULT_BATTLE_FORMAT):
    """Sends a challenge using the provided player object."""
    # Check player state *before* attempting
    player_name = getattr(player, 'username', 'unknown player')
    is_connected = getattr(player, 'connected', False)
    is_logged_in = getattr(player, 'logged_in', False)
    print(f"Sending invite: Player={player_name}, Connected={is_connected}, LoggedIn={is_logged_in}")

    if not is_connected or not is_logged_in:
         # Maybe try to reconnect or log in here if poke-env supports it easily?
         # await player.log_in(player.account_configuration.username, player.account_configuration.password) # Example
         return f"Error: Player {player_name} is not connected or logged in."

    if player is None: # Should be caught before calling
        return "Error: The selected player is not available/initialized."
    if not username or not username.strip():
        return "Error: Please enter a valid Showdown username."

    try:
        print(f"Attempting to send challenge from {player.username} to {username} in format {battle_format}")
        # Ensure challenge format is correct if needed
        # Check player._battle_format vs battle_format if necessary
        await player.send_challenges(username, n_challenges=1) # Pass format if needed
        return f"Battle invitation ({battle_format}) sent to {username} from bot {player.username}! Check Showdown."
    except Exception as e:
        print(f"Error sending challenge from {player_name}:")
        traceback.print_exc() # Print full stack trace
        # Consider what state the player might be in now.
        # Resetting the player state might be needed but is complex.
        return f"Error sending challenge: {str(e)}. Check console logs."

# Wrapper for Gradio (Revised)
def invite_to_battle(agent_choice: str, username: str):
    """Selects the agent and initiates the battle invitation via the background loop."""
    global random_player, openai_agent, agents_initialized, poke_env_loop

    if not agents_initialized or poke_env_loop is None or not poke_env_loop.is_running():
        # Maybe try starting again? Or just inform user.
        start_poke_env_thread() # Attempt to start if not running
        return "Agents are not ready or the background process is not running. Please wait a moment and try again."

    selected_player: Player | None = None
    if agent_choice == "Random Player":
        selected_player = random_player
        if selected_player is None:
            return "Error: Random Player is not available. Initialization might have failed."
    elif agent_choice == "OpenAI Agent":
        selected_player = openai_agent
        if selected_player is None:
            return "Error: OpenAI Agent not available. Check initialization logs and SHOWDOWN_PSWD."
    else:
        return "Error: Invalid agent choice selected."

    username_clean = username.strip()
    if not username_clean:
        return "Please enter your Showdown username."

    # Ensure we have a valid player before proceeding
    if selected_player is None:
         # This case should ideally be caught by the checks above, but double-check.
         return "Error: Could not select a valid player agent."

    # --- Crucial Change: Use run_coroutine_threadsafe ---
    try:
        # Schedule the async function on the dedicated poke-env loop
        future = asyncio.run_coroutine_threadsafe(
            send_battle_invite_async(selected_player, username_clean, DEFAULT_BATTLE_FORMAT),
            poke_env_loop
        )
        # Wait for the result from the background loop with a timeout
        result = future.result(timeout=30) # Adjust timeout as needed
        return result
    except TimeoutError:
        print(f"Timeout waiting for challenge result from {getattr(selected_player, 'username', agent_choice)}")
        return "Error: Sending challenge timed out. The bot might be busy or disconnected."
    except Exception as e:
        # This catches errors in scheduling or retrieving the result,
        # or unexpected errors from the coroutine itself if not caught internally.
        print(f"Unexpected error in invite_to_battle scheduling/execution: {e}")
        traceback.print_exc()
        return f"An unexpected error occurred: {e}"


# --- Gradio UI Definition (Mostly Unchanged) ---
iframe_code = """<iframe src="https://jofthomas.com/play.pokemonshowdown.com/testclient.html" width="100%" height="800" style="border: none;" referrerpolicy="no-referrer"></iframe>"""

def main_app():
    """Creates and returns the Gradio application interface."""
    # Start the background thread and loop when the app starts
    start_poke_env_thread()

    with gr.Blocks(title="Pokemon Showdown Agent") as demo:
        # ... (rest of your UI definition is likely fine) ...
        gr.Markdown("# Pokémon Battle Agent")

        agent_dropdown = gr.Dropdown(
            label="Select Agent",
            choices=["Random Player", "OpenAI Agent"], 
            value="Random Player",
            scale=1
        )
        name_input = gr.Textbox(...)
        battle_button = gr.Button(...)
        gr.Markdown("### Pokémon Showdown Interface")
        gr.Markdown("Log in/use the username you entered above.")
        gr.HTML(iframe_code)

        battle_button.click(
            fn=invite_to_battle,
            inputs=[agent_dropdown, name_input],
            outputs=gr.Textbox(label="Status") # Add an output Textbox to display results/errors
        )
      

    return demo

# --- Main execution block ---
if __name__ == "__main__":
    app = main_app()
    # Add proper app closing logic if needed to shut down the loop/thread gracefully
    # For simple cases, daemon thread might be enough, but explicit shutdown is better.
    app.launch()