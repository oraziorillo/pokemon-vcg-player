# app.py
import gradio as gr
import asyncio
import threading # Still needed for asyncio.run in sync context potentially
import os
import random
import traceback # For detailed error logging

# Import poke-env components
from poke_env.player import Player, RandomPlayer
from poke_env import AccountConfiguration, ServerConfiguration
# Import your custom agent
from agents import OpenAIAgent # Assuming agents.py exists with OpenAIAgent

# --- Configuration ---
# Use your custom server or the official Smogon server
# custom_config = ServerConfiguration(
#     "wss://jofthomas.com/showdown/websocket", # WebSocket URL
#     "https://jofthomas.com/showdown/action.php" # Authentication URL
# )
# Or use the default Smogon server configuration
custom_config = ServerConfiguration.get_default() # Easier for general use

# --- Dynamic Account Configuration ---
RANDOM_PLAYER_BASE_NAME = "TempRandAgent" # Changed base name slightly
OPENAI_AGENT_BASE_NAME = "TempOpenAIAgent" # Changed base name slightly
DEFAULT_BATTLE_FORMAT = "gen9randombattle"

# --- Agent Creation (Per Request) ---
async def create_agent_async(agent_type: str, battle_format: str = DEFAULT_BATTLE_FORMAT) -> Player | str:
    """
    Creates and initializes a *single* agent instance with a unique username.
    Returns the Player object on success, or an error string on failure.
    """
    print(f"Attempting to create agent of type: {agent_type}")
    player: Player | None = None
    error_message: str | None = None

    # Generate a unique suffix for this instance
    agent_suffix = random.randint(10000, 999999) # Wider range for uniqueness

    try:
        if agent_type == "Random Player":
            username = f"{RANDOM_PLAYER_BASE_NAME}{agent_suffix}"
            account_config = AccountConfiguration(username, None) # Guest account
            print(f"Initializing RandomPlayer with username: {username}")
            player = RandomPlayer(
                account_configuration=account_config,
                server_configuration=custom_config,
                battle_format=battle_format,
                # Add a start_listening=False initially if needed, manage connection explicitly
                # start_listening=False # Let's try without first
            )
            # await player.connect() # Explicit connect might be needed if start_listening=False

        elif agent_type == "OpenAI Agent":
            # Check for API key early
            if not os.getenv("OPENAI_API_KEY"):
                 error_message = "Error: Cannot create OpenAI Agent. OPENAI_API_KEY environment variable is missing."
                 print(error_message)
                 return error_message # Return early

            username = f"{OPENAI_AGENT_BASE_NAME}{agent_suffix}"
            account_config = AccountConfiguration(username, None) # Guest account
            print(f"Initializing OpenAIAgent with username: {username}")
            player = OpenAIAgent( # Make sure your OpenAIAgent accepts these args
                account_configuration=account_config,
                server_configuration=custom_config,
                battle_format=battle_format,
                # start_listening=False
            )
            # await player.connect()

        else:
            error_message = f"Error: Invalid agent type '{agent_type}' requested."
            print(error_message)
            return error_message

        # A short wait might be necessary for the player to establish connection/login
        # This is often handled implicitly by poke-env's internal loops when
        # start_listening=True (default), but managing explicitly can be complex.
        # Let's rely on send_challenges potentially waiting if needed.
        # await asyncio.sleep(2) # Add small delay only if connection issues arise

        print(f"Agent ({username}) created successfully (object: {player}).")
        return player # Return the player instance

    except Exception as e:
        agent_name = username if 'username' in locals() else agent_type
        error_message = f"Error creating agent {agent_name}: {e}"
        print(error_message)
        traceback.print_exc() # Log detailed error
        # Ensure cleanup if partial creation occurred (less likely without start_listening=False)
        # if player and hasattr(player, 'disconnect'):
        #     try:
        #         await player.disconnect()
        #     except Exception as disconnect_e:
        #         print(f"Error during cleanup disconnect: {disconnect_e}")
        return error_message # Return the error string

# --- Battle Invitation Logic (Remains mostly the same, uses the created player) ---
async def send_battle_invite_async(player: Player, opponent_username: str, battle_format: str):
    """Sends a challenge using the provided player object."""
    # Player should already be created and potentially connected by create_agent_async
    if not isinstance(player, Player):
         # This case should ideally be caught earlier, but adding safety check
         return f"Error: Invalid player object passed to send_battle_invite_async: {player}"

    player_username = getattr(player, 'username', 'unknown_agent') # Get username safely

    try:
        print(f"Attempting to send challenge from {player_username} to {opponent_username} in format {battle_format}")
        # Ensure the player's connection is ready if not automatically handled.
        # If using start_listening=False, ensure player.connect() was called and awaited.
        # The send_challenges method might handle waiting for login internally.
        await player.send_challenges(opponent_username, n_challenges=1, packed_team=None, battle_format=battle_format) # Specify format if needed
        print(f"Challenge sent successfully from {player_username} to {opponent_username}.")
        return f"Battle invitation ({battle_format}) sent to {opponent_username} from bot {player_username}! Check Showdown."

    except Exception as e:
        print(f"Error sending challenge from {player_username}:")
        traceback.print_exc()
        return f"Error sending challenge from {player_username}: {str(e)}. Check console logs."

    # --- No explicit disconnect here - let the scope manage it ---
    # finally:
    #     # Attempt to disconnect the temporary agent after the challenge is sent (or fails)
    #     if player and hasattr(player, 'disconnect'):
    #          print(f"Disconnecting temporary agent: {player_username}")
    #          try:
    #              await player.disconnect()
    #          except Exception as disconnect_e:
    #              print(f"Error disconnecting {player_username}: {disconnect_e}")


# --- Gradio Interface Function (Sync Wrapper) ---
def invite_to_battle(agent_choice: str, username: str):
    """
    Handles the Gradio button click: Creates an agent, sends invite, and returns status.
    This function is SYNCHRONOUS as required by Gradio's fn handler.
    """
    username_clean = username.strip()
    if not username_clean:
        return "Please enter your Showdown username."
    if not agent_choice:
        return "Please select an agent type."

    # Define the async tasks to be run for this request
    async def _run_async_tasks(selected_agent_type, target_username):
        # 1. Create the agent for this specific request
        agent_or_error = await create_agent_async(selected_agent_type, DEFAULT_BATTLE_FORMAT)

        if isinstance(agent_or_error, str): # Check if creation returned an error string
            return agent_or_error # Return the error message from creation

        # 2. If agent created successfully, send the challenge
        player_instance = agent_or_error
        result = await send_battle_invite_async(player_instance, target_username, DEFAULT_BATTLE_FORMAT)

        # 3. poke-env usually handles cleanup when the player object goes out of scope
        # or the event loop managing it finishes, especially with asyncio.run.
        # If persistent connection issues arise, explicit player.disconnect() might
        # be needed within send_battle_invite_async's finally block or here.
        print(f"Async task for {getattr(player_instance, 'username', 'agent')} completed.")
        return result

    # Run the async tasks within the synchronous Gradio handler
    try:
        # asyncio.run creates a new event loop, runs the coroutine, and closes the loop.
        # This is suitable for managing the short lifecycle of the temporary agent.
        print(f"Starting async task execution for request: {agent_choice} vs {username_clean}")
        result = asyncio.run(_run_async_tasks(agent_choice, username_clean))
        print(f"Async task finished. Result: {result}")
        return result
    except RuntimeError as e:
        # Handle cases where asyncio.run might conflict (e.g., nested loops, rare)
         print(f"RuntimeError during asyncio.run: {e}")
         traceback.print_exc()
         # Check if it's the "cannot run loop while another is running" error
         if "cannot run loop" in str(e):
              return "Error: Could not execute task due to conflicting event loop activity. Please try again."
         else:
              return f"An unexpected runtime error occurred: {e}"
    except Exception as e:
        print(f"Unexpected error in invite_to_battle sync wrapper: {e}")
        traceback.print_exc()
        return f"An critical error occurred: {e}"


# --- Gradio UI Definition (No changes needed here) ---
# iframe code to embed Pokemon Showdown (using a potentially more stable client link if needed)
iframe_code = """
<iframe
    src="https://play.pokemonshowdown.com/"
    width="100%"
    height="800"
    style="border: none;"
    referrerpolicy="no-referrer">
</iframe>
"""
# Note: Changed iframe src to the main client. If your custom server needs a specific
# client URL like the one you had, change it back. Ensure CORS/embedding is allowed.

def main_app():
    """Creates and returns the Gradio application interface."""
    # NO agent initialization at startup anymore
    # start_agent_initialization() # REMOVED

    with gr.Blocks(title="Pokemon Showdown Agent") as demo:
        gr.Markdown("# Pokémon Battle Agent")
        gr.Markdown(
            "Select an agent, enter **your** Showdown username "
            "(the one you are logged in with below), and click Send Invite. "
            "A temporary bot with a unique name will be created for the challenge."
        )

        with gr.Row():
            agent_dropdown = gr.Dropdown(
                label="Select Agent",
                choices=["Random Player", "OpenAI Agent"],
                value="Random Player",
                scale=1
            )
            name_input = gr.Textbox(
                label="Your Pokémon Showdown Username",
                placeholder="Enter username used in Showdown below",
                scale=2
            )
            battle_button = gr.Button("Send Battle Invitation", scale=1)

        # --- Display area for status/results ---
        status_output = gr.Textbox(label="Status", interactive=False) # Added output field

        gr.Markdown("### Pokémon Showdown Interface")
        gr.Markdown("Log in/use the username you entered above.")
        gr.HTML(iframe_code)

        battle_button.click(
            fn=invite_to_battle,
            inputs=[agent_dropdown, name_input],
            outputs=[status_output] # Connect output to the status box
        )

    return demo

# --- Main execution block ---
if __name__ == "__main__":
    # Set OPENAI_API_KEY environment variable if needed, e.g., using python-dotenv
    # from dotenv import load_dotenv
    # load_dotenv()
    # if not os.getenv("OPENAI_API_KEY"):
    #    print("Warning: OPENAI_API_KEY not set. OpenAI Agent will not work.")

    app = main_app()
    # Consider server_name/port for accessibility if running locally
    # app.launch(server_name="0.0.0.0", server_port=7860)
    app.launch()