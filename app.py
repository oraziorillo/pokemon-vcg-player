# app.py
import gradio as gr
import asyncio
import os
import random
import traceback
import logging
import threading # Import threading

# --- [ Previous code for imports, configuration, logging setup remains the same ] ---
# Import poke-env components
from poke_env.player import Player, RandomPlayer
from poke_env import AccountConfiguration, ServerConfiguration
# Import your custom agent(s)
from agents import OpenAIAgent # Assuming agents.py exists with OpenAIAgent

# --- Configuration ---
POKE_SERVER_URL = "wss://jofthomas.com/showdown/websocket"
POKE_AUTH_URL = "https://jofthomas.com/showdown/action.php"
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(threadName)s - %(levelname)s - %(message)s')

# --- Constants ---
RANDOM_PLAYER_BASE_NAME = "RandAgent"
OPENAI_AGENT_BASE_NAME = "OpenAIAgent"
DEFAULT_BATTLE_FORMAT = "gen9randombattle"
custom_config = ServerConfiguration(POKE_SERVER_URL, POKE_AUTH_URL)


# button HEX code
my_hex_color = "#ffca19" # Example: Orange
# text color
my_text_color = "#FFFFFF" # Example: White


# --- Agent Creation (Async - Required by poke-env) ---
# [ create_agent_async function remains exactly the same as the previous version ]
async def create_agent_async(agent_type: str, battle_format: str = DEFAULT_BATTLE_FORMAT) -> Player | str:
    """
    Creates and initializes a SINGLE agent instance with a unique username.
    This function MUST be async because Player initialization involves async network setup.
    Returns the Player object on success, or an error string on failure.
    """
    logging.info(f"Attempting to create agent of type: {agent_type}")
    player: Player | None = None
    error_message: str | None = None
    username: str = "unknown_agent" # Default for logging in case of early failure

    agent_suffix = random.randint(10000, 999999)

    try:
        if agent_type == "Random Player":
            username = f"{RANDOM_PLAYER_BASE_NAME}{agent_suffix}"
            account_config = AccountConfiguration(username, None)
            logging.info(f"Initializing RandomPlayer with username: {username}")
            player = RandomPlayer(
                account_configuration=account_config,
                server_configuration=custom_config,
                battle_format=battle_format,
                start_listening=True,
            )
        elif agent_type == "OpenAI Agent":
            if not os.getenv("OPENAI_API_KEY"):
                 error_message = "Error: Cannot create OpenAI Agent. OPENAI_API_KEY environment variable is missing."
                 logging.error(error_message)
                 return error_message
            username = f"{OPENAI_AGENT_BASE_NAME}{agent_suffix}"
            account_config = AccountConfiguration(username, None)
            logging.info(f"Initializing OpenAIAgent with username: {username}")
            player = OpenAIAgent(
                account_configuration=account_config,
                server_configuration=custom_config,
                battle_format=battle_format,
                start_listening=True,
            )
        else:
            error_message = f"Error: Invalid agent type '{agent_type}' requested."
            logging.error(error_message)
            return error_message

        logging.info(f"Agent object ({username}) created successfully.")
        return player

    except Exception as e:
        error_message = f"Error creating agent {username}: {e}"
        logging.error(error_message)
        logging.error(traceback.format_exc())
        return error_message

# --- Battle Invitation (Async - Required by poke-env) ---
# [ send_battle_invite_async function remains exactly the same as the previous version ]
async def send_battle_invite_async(player: Player, opponent_username: str, battle_format: str) -> str:
    """
    Sends a challenge using the provided player object.
    This function MUST be async as sending challenges involves network I/O.
    Returns a status string (success or error message).
    """
    if not isinstance(player, Player):
         err_msg = f"Internal Error: Invalid object passed instead of Player: {type(player)}"
         logging.error(err_msg)
         # In background thread, we might just log this and exit thread
         raise TypeError(err_msg) # Raise exception to be caught by the thread runner

    player_username = getattr(player, 'username', 'unknown_agent')

    try:
        logging.info(f"Attempting to send challenge from {player_username} to {opponent_username} in format {battle_format}")
        await player.send_challenges(opponent_username, n_challenges=1)
        success_msg = f"Battle invitation ({battle_format}) sent to '{opponent_username}' from bot '{player_username}'."
        logging.info(success_msg)
        return success_msg # Indicate success

    except Exception as e:
        error_msg = f"Error sending challenge from {player_username} to {opponent_username}: {e}"
        logging.error(error_msg)
        logging.error(traceback.format_exc())
        # Re-raise or return error indication for the thread runner
        raise e # Raise exception to be caught by the thread runner


# --- Background Task Runner (Runs in a separate thread) ---
def run_invite_in_background(agent_choice: str, target_username: str, battle_format: str):
    """
    This function runs in a separate thread for each invite request.
    It sets up and runs the asyncio operations needed for one invite.
    """
    thread_name = threading.current_thread().name
    logging.info(f"Background thread '{thread_name}' started for {agent_choice} vs {target_username}.")

    async def _run_async_challenge_steps():
        """The async steps to be run via asyncio.run() in this thread."""
        agent_or_error = await create_agent_async(agent_choice, battle_format)

        if isinstance(agent_or_error, str):
            # Agent creation failed, log the error message from create_agent_async
            logging.error(f"[{thread_name}] Agent creation failed: {agent_or_error}")
            # No further action needed in this thread
            return

        player_instance: Player = agent_or_error
        player_username = getattr(player_instance, 'username', 'agent')
        logging.info(f"[{thread_name}] Agent {player_username} created, proceeding to challenge {target_username}.")

        try:
            result = await send_battle_invite_async(player_instance, target_username, battle_format)
            # Log the success message from send_battle_invite_async
            logging.info(f"[{thread_name}] Challenge result: {result}")
        except Exception as invite_error:
            # Log errors from send_battle_invite_async
            # Error message/traceback already logged inside send_battle_invite_async
            logging.error(f"[{thread_name}] Failed to send challenge from {player_username} to {target_username}. Error: {invite_error}")
        finally:
            pass

    try:
        asyncio.run(_run_async_challenge_steps())
        logging.info(f"Background thread '{thread_name}' finished successfully for {target_username}.")
    except RuntimeError as e:
         logging.error(f"[{thread_name}] asyncio RuntimeError: {e}")
         logging.error(traceback.format_exc())
    except Exception as e:
        logging.error(f"[{thread_name}] Unexpected error in background task: {e}")
        logging.error(traceback.format_exc())

# --- Gradio Interface Logic (Starts the background thread) ---
def start_invite_thread(agent_choice: str, username: str) -> str:
    """
    Handles the Gradio button click (Synchronous, but FAST).
    Performs basic validation and starts a background thread to handle
    the actual agent creation and invitation process.
    Returns an immediate status message to Gradio.
    """
    username_clean = username.strip()
    if not username_clean:
        return "⚠️ Please enter your Showdown username."
    if not agent_choice:
        return "⚠️ Please select an agent type."

    logging.info(f"Received request: Agent={agent_choice}, Opponent={username_clean}. Starting background thread.")

    # Create and start the background thread
    thread = threading.Thread(
        target=run_invite_in_background,
        args=(agent_choice, username_clean, DEFAULT_BATTLE_FORMAT),
        daemon=True # Set as daemon so threads don't block app exit
    )
    thread.start()

    # Return immediately to Gradio UI
    return f"✅ Invite process for '{username_clean}' started in background. Check Pokémon Showdown and logs for status."


# --- Gradio UI Definition ---
# [ main_app function remains the same, but the button click now calls start_invite_thread ]
def main_app():
    """Creates and returns the Gradio application interface."""

    agent_options = ["Random Player"]
    agent_options.append("OpenAI Agent")

    # Use a more descriptive title if possible
    with gr.Blocks(title="Pokemon Showdown Multi-Challenger") as demo:
        gr.Markdown("# Pokémon Battle Agent Challenger")
        gr.Markdown(
            "1. Choose a name in the Iframe, if you have an account, you can also connect.\n"
            "2. Select an agent type.\n"
            "3. Enter **your** Showdown username (the one you are logged in with below).\n"
            "4. Click 'Send Battle Invitation'. You can click multiple times for different users.\n\n"
            "A temporary bot will be created *in the background* to send the challenge in `gen9randombattle` format."
        )

        with gr.Row():
            agent_dropdown = gr.Dropdown(
                label="Select Agent", choices=agent_options, value=agent_options[0], scale=1
            )
            name_input = gr.Textbox(
                label="Your Pokémon Showdown Username", placeholder="Enter username used in Showdown below", scale=2
            )
          
            battle_button = gr.Button(
                "Send Battle Invitation",
                variant="primary", # Keep variant or remove if CSS overrides all styles
                scale=1,
                elem_id="custom-color-button" # Assign a unique ID
            )
            
            # 2. The required CSS (place this *within* the same gr.Blocks() context)
            #    This targets the button using its ID.
            #    You might need !important to override Gradio's default theme styles.
            #    Adjust text color ('color') for readability against your chosen background.
            gr.CSS(f"""
                #custom-color-button {{
                    background-color: {my_hex_color} !important;
                    color: {my_text_color} !important;
                    border: none !important; /* Optional: remove border */
                    /* Add other styles like border-radius if needed */
                }}
                /* Optional: Style for hover effect */
                #custom-color-button:hover {{
                    background-color: darken({my_hex_color}, 10%) !important; /* Make it slightly darker on hover */
                }}
            """)
        gr.HTML("""
        <iframe
            src="https://jofthomas.com/play.pokemonshowdown.com/testclient.html"
            width="100%" height="800" style="border: none;" referrerpolicy="no-referrer">
        </iframe>
        """)

        # *** IMPORTANT: Update the click handler ***
        battle_button.click(
            fn=start_invite_thread, # Calls the function that starts the thread
            inputs=[agent_dropdown, name_input],
        )

    return demo

# --- Application Entry Point ---
# [ if __name__ == "__main__": block remains the same ]
if __name__ == "__main__":
    app = main_app()
    app.launch()