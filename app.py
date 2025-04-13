# app.py
import gradio as gr
import asyncio
import threading 
import os
import random
import traceback 

# Import poke-env components
from poke_env.player import Player, RandomPlayer
from poke_env import AccountConfiguration, ServerConfiguration
# Import your custom agent(s)
from agents import OpenAIAgent # Assuming agents.py exists with OpenAIAgent

# --- Configuration ---
# Don't change this as this is the official server running Hugging Face servers
custom_config = ServerConfiguration(
    "wss://jofthomas.com/showdown/websocket", # WebSocket URL
    "https://jofthomas.com/showdown/action.php" # Authentication URL
)


# --- Dynamic Account Configuration ---
RANDOM_PLAYER_BASE_NAME = "RandAgent" 
OPENAI_AGENT_BASE_NAME = "OpenAIAgent" 
DEFAULT_BATTLE_FORMAT = "gen9randombattle"


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
                
            )

        elif agent_type == "OpenAI Agent":
            if not os.getenv("OPENAI_API_KEY"):
                 error_message = "Error: Cannot create OpenAI Agent. OPENAI_API_KEY environment variable is missing."
                 print(error_message)
                 return error_message 

            username = f"{OPENAI_AGENT_BASE_NAME}{agent_suffix}"
            account_config = AccountConfiguration(username, None) # Guest account
            print(f"Initializing OpenAIAgent with username: {username}")
            player = OpenAIAgent( 
                account_configuration=account_config,
                server_configuration=custom_config,
                battle_format=battle_format,
                
            )

        else:
            error_message = f"Error: Invalid agent type '{agent_type}' requested."
            print(error_message)
            return error_message

        print(f"Agent ({username}) created successfully (object: {player}).")
        return player # Return the player instance

    except Exception as e:
        agent_name = username if 'username' in locals() else agent_type
        error_message = f"Error creating agent {agent_name}: {e}"
        print(error_message)
        traceback.print_exc() 
        return error_message # Return the error string

async def send_battle_invite_async(player: Player, opponent_username: str, battle_format: str):
    """Sends a challenge using the provided player object."""
    if not isinstance(player, Player):
         return f"Error: Invalid player object passed to send_battle_invite_async: {player}"

    player_username = getattr(player, 'username', 'unknown_agent')

    try:
        print(f"Attempting to send challenge from {player_username} to {opponent_username} in format {battle_format}")
        await player.send_challenges(opponent_username, n_challenges=1, packed_team=None, battle_format=battle_format) # Specify format if needed
        print(f"Challenge sent successfully from {player_username} to {opponent_username}.")
        return f"Battle invitation ({battle_format}) sent to {opponent_username} from bot {player_username}! Check Showdown."

    except Exception as e:
        print(f"Error sending challenge from {player_username}:")
        traceback.print_exc()
        return f"Error sending challenge from {player_username}: {str(e)}. Check console logs."

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

    async def _run_async_tasks(selected_agent_type, target_username):
        agent_or_error = await create_agent_async(selected_agent_type, DEFAULT_BATTLE_FORMAT)

        if isinstance(agent_or_error, str): 
            return agent_or_error 

        player_instance = agent_or_error
        result = await send_battle_invite_async(player_instance, target_username, DEFAULT_BATTLE_FORMAT)
        print(f"Async task for {getattr(player_instance, 'username', 'agent')} completed.")
        return result

    try:
        print(f"Starting async task execution for request: {agent_choice} vs {username_clean}")
        result = asyncio.run(_run_async_tasks(agent_choice, username_clean))
        print(f"Async task finished. Result: {result}")
        return result
    except RuntimeError as e:
         print(f"RuntimeError during asyncio.run: {e}")
         traceback.print_exc()
         if "cannot run loop" in str(e):
              return "Error: Could not execute task due to conflicting event loop activity. Please try again."
         else:
              return f"An unexpected runtime error occurred: {e}"
    except Exception as e:
        print(f"Unexpected error in invite_to_battle sync wrapper: {e}")
        traceback.print_exc()
        return f"An critical error occurred: {e}"


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

        status_output = gr.Textbox(label="Status", interactive=False)

        gr.Markdown("### Pokémon Showdown Interface")
        gr.Markdown("Log in/use the username you entered above.")
        gr.HTML(iframe_code)

        battle_button.click(
            fn=invite_to_battle,
            inputs=[agent_dropdown, name_input],
            outputs=[status_output] # Connect output to the status box
        )

    return demo

if __name__ == "__main__":
  
    app = main_app()
    app.launch()