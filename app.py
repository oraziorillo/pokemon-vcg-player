# app_twitch_sequential.py
import gradio as gr
import asyncio
import os
# import requests # Not used currently
# import json # Not used currently
from typing import List, AsyncGenerator, Dict, Optional, Tuple
import logging
import traceback
import time
import random
import re

# --- Imports for poke_env and agents ---
from poke_env.player import Player
from poke_env import AccountConfiguration, ServerConfiguration
from poke_env.environment.battle import Battle

# Import your custom agent (Placeholder included)
try:
    from agents import OpenAIAgent
    # from agents import GeminiAgent, MistralAgent
except ImportError:
    print("ERROR: Could not import OpenAIAgent from agents.py. Using placeholder.")
    class OpenAIAgent(Player):
        # Placeholder Init - Ensure it mimics essential parts if needed later
        def __init__(self, *args, max_concurrent_battles=None, **kwargs):
            super().__init__(*args, max_concurrent_battles=max_concurrent_battles, **kwargs)
            print(f"Placeholder Agent {self.username} initialized.")
            self.last_error = None # Add last_error for compatibility

        def choose_move(self, battle: Battle):
            # Placeholder Move Selection
            print(f"Placeholder Agent {self.username}: Choosing first available move.")
            if battle.available_moves: return self.create_order(battle.available_moves[0])
            else: return self.choose_random_move(battle)

# --- Configuration ---
CUSTOM_SERVER_URL = "wss://jofthomas.com/showdown/websocket"
CUSTOM_ACTION_URL = 'https://play.pokemonshowdown.com/action.php?'
CUSTOM_BATTLE_VIEW_URL_TEMPLATE = "https://jofthomas.com/play.pokemonshowdown.com/testclient.html?nocache=true#{battle_id}"
custom_config = ServerConfiguration(CUSTOM_SERVER_URL, CUSTOM_ACTION_URL)
DEFAULT_BATTLE_FORMAT = "gen9randombattle"
# NUM_INVITES_TO_ACCEPT_PER_AGENT = 1 # Now implicit in accept_challenges(None, 1)

AGENT_CONFIGS = {
    "OpenAIAgent": {"class": OpenAIAgent, "password_env_var": "OPENAI_AGENT_PASSWORD"},
    "GeminiAgent": {"class": OpenAIAgent, "password_env_var": "GEMINI_AGENT_PASSWORD"},
    "MistralAgent": {"class": OpenAIAgent, "password_env_var": "MISTRAL_AGENT_PASSWORD"},
}
# Filter out agents with missing passwords at the start
AVAILABLE_AGENT_NAMES = [
    name for name, cfg in AGENT_CONFIGS.items()
    if os.environ.get(cfg.get("password_env_var", ""))
]
if not AVAILABLE_AGENT_NAMES:
    print("FATAL ERROR: No agent configurations have their required password environment variables set. Exiting.")
    # exit(1) # Or handle gracefully in Gradio

# --- Global State Variables for Sequential Lifecycle ---
active_agent_name: Optional[str] = None
active_agent_instance: Optional[Player] = None
active_agent_task: Optional[asyncio.Task] = None # Task for accept_challenges(None, 1)
current_battle_instance: Optional[Battle] = None

background_task_handle: Optional[asyncio.Task] = None # To hold the main background task

# --- State variable for HTML display ---
current_display_html: str = """
    <div style='display: flex; justify-content: center; align-items: center; height: 99vh; background-color: #eee; font-family: sans-serif;'>
        <p style='font-size: 1.5em;'>Initializing Stream Display...</p>
    </div>"""
REFRESH_INTERVAL_SECONDS = 3 # Check state more frequently

# --- Helper Functions ---
def get_active_battle(agent: Player) -> Optional[Battle]:
    """Returns the first non-finished battle for an agent."""
    if agent and agent._battles:
        # Ensure agent._battles is accessed correctly
        active_battles = [b for b in agent._battles.values() if not b.finished]
        if active_battles:
            if active_battles[0].battle_tag: return active_battles[0]
            else: print(f"WARN: Found active battle for {agent.username} but it has no battle_tag yet."); return None
    return None

def create_battle_iframe(battle_id: str) -> str:
    """Creates the HTML for the battle iframe."""
    timestamp = int(time.time() * 1000)
    base_template, _, fragment_template = CUSTOM_BATTLE_VIEW_URL_TEMPLATE.partition('#')
    formatted_fragment = fragment_template.format(battle_id=battle_id)
    # Add cache busting to both the URL and as a query parameter
    battle_url_with_query = f"{base_template}?cachebust={timestamp}#{formatted_fragment}"
    print(f"Generating iframe for URL: {battle_url_with_query}")
    
    # Add more attributes to help with iframe refreshing and performance
    return f"""
    <iframe 
        src="{battle_url_with_query}" 
        width="100%" 
        height="99vh" 
        style="border: none; margin: 0; padding: 0; display: block;" 
        referrerpolicy="no-referrer"
        allow="autoplay; fullscreen"
        importance="high"
        loading="eager"
        sandbox="allow-same-origin allow-scripts allow-popups allow-forms"
        onload="this.contentWindow.location.reload(true);"
    ></iframe>
    """

def create_idle_html(status_message: str, instruction: str) -> str:
    """Creates a visually appealing idle screen HTML with improved readability and local background."""
    # Use the local image file served by Gradio
    background_image_url = "/file=pokemon_huggingface.png" # Gradio path for local files

    return f"""
        <div style="
            display: flex; flex-direction: column; justify-content: center; align-items: center;
            height: 99vh; width: 100%;
            background-image: url('{background_image_url}'); background-size: cover; background-position: center;
            border: none; margin: 0; padding: 20px;
            text-align: center; font-family: sans-serif; color: white;
            box-sizing: border-box;">
            <div style="background-color: rgba(0, 0, 0, 0.65); padding: 30px; border-radius: 15px; max-width: 80%;">
                <p style="font-size: 2.5em; margin-bottom: 20px; text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.8);">{status_message}</p>
                <p style="font-size: 1.5em; text-shadow: 1px 1px 3px rgba(0, 0, 0, 0.8);">{instruction}</p>
            </div>
        </div>"""

def create_error_html(error_msg: str) -> str:
    """Creates HTML to display an error message."""
    # Using create_idle_html structure for consistency, but with error styling
    return f"""
        <div style="
            display: flex; flex-direction: column; justify-content: center; align-items: center;
            height: 99vh; width: 100%; background-color: #330000; /* Dark red background */
            border: none; margin: 0; padding: 20px;
            text-align: center; font-family: sans-serif; color: white;
            box-sizing: border-box;">
            <div style="background-color: rgba(200, 0, 0, 0.7); padding: 30px; border-radius: 15px; max-width: 80%;">
                <p style="font-size: 2em; margin-bottom: 20px;">An Error Occurred</p>
                <p style="font-size: 1.2em; color: #ffdddd;">{error_msg}</p>
            </div>
        </div>"""
# --- End Helper Functions ---


# --- Agent Lifecycle Management ---
async def select_and_activate_new_agent():
    """Selects a random available agent, instantiates it, and starts its listening task."""
    global active_agent_name, active_agent_instance, active_agent_task, current_display_html

    if not AVAILABLE_AGENT_NAMES:
        print("Lifecycle: No available agents with passwords set.")
        current_display_html = create_error_html("No agents available (check password env vars).")
        return False # Indicate failure

    selected_name = random.choice(AVAILABLE_AGENT_NAMES)
    config = AGENT_CONFIGS[selected_name]
    AgentClass = config["class"]
    password_env_var = config["password_env_var"]
    agent_password = os.environ.get(password_env_var)

    print(f"Lifecycle: Activating agent '{selected_name}'...")
    current_display_html = create_idle_html("Selecting Next Agent...", f"Preparing {selected_name}...")

    try:
        account_config = AccountConfiguration(selected_name, agent_password)
        agent = AgentClass(
            account_configuration=account_config,
            server_configuration=custom_config,
            battle_format=DEFAULT_BATTLE_FORMAT,
            log_level=logging.INFO, # Keep INFO for debugging startup
            max_concurrent_battles=1
        )
        agent.last_error = None # Initialize attribute

        # Start the task to accept exactly one battle challenge
        task = asyncio.create_task(agent.accept_challenges(None, 1), name=f"accept_challenge_{selected_name}")
        # Add callback for task completion/error
        task.add_done_callback(log_task_exception)

        # Update global state *after* successful creation and task launch
        active_agent_name = selected_name
        active_agent_instance = agent
        active_agent_task = task
        print(f"Lifecycle: Agent '{selected_name}' is active and listening for 1 challenge.")
        current_display_html = create_idle_html(f"Agent <strong>{selected_name}</strong> is ready!", f"Please challenge <strong>{selected_name}</strong> to a <strong>{DEFAULT_BATTLE_FORMAT}</strong> battle.")
        return True # Indicate success

    except Exception as e:
        error_msg = f"Failed to activate agent '{selected_name}': {e}"
        print(error_msg); traceback.print_exc()
        current_display_html = create_error_html(error_msg)
        # Ensure partial state is cleared if activation failed
        active_agent_name = None
        active_agent_instance = None
        active_agent_task = None
        return False # Indicate failure

async def check_for_new_battle():
    """Checks if the active agent has started a battle."""
    global active_agent_instance, current_battle_instance
    if active_agent_instance:
        battle = get_active_battle(active_agent_instance)
        if battle and battle.battle_tag:
            print(f"Lifecycle: Agent '{active_agent_name}' started battle: {battle.battle_tag}")
            current_battle_instance = battle
            # Prevent the agent from accepting more challenges immediately
            # (accept_challenges(n=1) should handle this, but belt-and-suspenders)
            if active_agent_task and not active_agent_task.done():
                print(f"Lifecycle: Cancelling accept_challenges task for {active_agent_name} as battle started.")
                active_agent_task.cancel()
        # else: print(f"Lifecycle: Agent {active_agent_name} still waiting for battle...") # Too noisy maybe

async def deactivate_current_agent(reason: str = "cycle"):
    """Cleans up the currently active agent and resets state."""
    global active_agent_name, active_agent_instance, active_agent_task, current_battle_instance, current_display_html

    print(f"Lifecycle: Deactivating agent '{active_agent_name}' (Reason: {reason})...")
    current_display_html = create_idle_html("Battle Finished" if reason=="battle_end" else "Resetting Agent", f"Preparing for next selection...")

    agent = active_agent_instance
    task = active_agent_task

    # Clear state first to prevent race conditions
    active_agent_name = None
    active_agent_instance = None
    active_agent_task = None
    current_battle_instance = None

    # Cancel the accept_challenges task if it's still running
    if task and not task.done():
        print(f"Lifecycle: Cancelling task for {agent.username if agent else 'unknown agent'}...")
        task.cancel()
        try:
            await asyncio.wait_for(task, timeout=2.0) # Give task time to process cancellation
        except asyncio.CancelledError:
            print(f"Lifecycle: Task cancellation confirmed.")
        except asyncio.TimeoutError:
            print(f"Lifecycle: Task did not confirm cancellation within timeout.")
        except Exception as e:
            print(f"Lifecycle: Error during task cancellation wait: {e}")


    # Disconnect the player
    if agent:
        print(f"Lifecycle: Disconnecting player {agent.username}...")
        try:
            # Check if websocket exists and is open before disconnecting
            if hasattr(agent, '_websocket') and agent._websocket and agent._websocket.open:
                 await agent.disconnect()
                 print(f"Lifecycle: Player {agent.username} disconnected.")
            else:
                 print(f"Lifecycle: Player {agent.username} already disconnected or websocket not ready.")
        except Exception as e:
            print(f"ERROR during agent disconnect ({agent.username}): {e}")
            # Continue cleanup even if disconnect fails

    print(f"Lifecycle: Agent deactivated.")

# --- End Agent Lifecycle Management ---

# --- Main Background Task (Enhanced Logging) ---
async def manage_agent_lifecycle():
    """Runs the main loop selecting, running, and cleaning up agents sequentially."""
    global current_display_html, active_agent_instance, active_agent_task, current_battle_instance

    print("Background lifecycle manager started.")
    await asyncio.sleep(2) # Initial delay

    loop_counter = 0
    while True:
        loop_counter += 1
        try:
            print(f"\n--- Lifecycle Check #{loop_counter} [{time.strftime('%H:%M:%S')}] ---") # Add loop counter and timestamp
            agent_state = f"State: Agent={active_agent_name}, TaskRunning={not active_agent_task.done() if active_agent_task else 'N/A'}, BattleMonitored={current_battle_instance is not None}"
            print(agent_state)
            previous_html_start = current_display_html[:60] # Store start of previous HTML

            # State 1: No agent is active
            if active_agent_instance is None:
                print(f"[{loop_counter}] State 1: No active agent. Selecting...")
                activated = await select_and_activate_new_agent()
                if not activated:
                    print(f"[{loop_counter}] State 1: Activation failed. Waiting.")
                    await asyncio.sleep(10); continue
                print(f"[{loop_counter}] State 1: Agent '{active_agent_name}' activated.")
                # select_and_activate_new_agent sets the initial idle HTML

            # State 2: Agent is active
            else:
                print(f"[{loop_counter}] State 2: Agent '{active_agent_name}' active.")
                # Check task status first
                if active_agent_task and active_agent_task.done():
                    # ... (error/completion handling as before) ...
                    print(f"[{loop_counter}] State 2: Task done/error. Deactivating {active_agent_name}.")
                    await deactivate_current_agent(reason="task_done_or_error"); continue

                # Check for battle start if not monitoring
                if current_battle_instance is None:
                    print(f"[{loop_counter}] State 2: Checking for new battle...")
                    await check_for_new_battle()
                    if current_battle_instance:
                         print(f"[{loop_counter}] State 2: *** NEW BATTLE DETECTED: {current_battle_instance.battle_tag} ***")
                    # else: print(f"[{loop_counter}] State 2: No new battle detected.")

                # State 2a: Battle is monitored
                if current_battle_instance is not None:
                    battle_tag = current_battle_instance.battle_tag
                    print(f"[{loop_counter}] State 2a: Monitoring battle {battle_tag}")
                    battle_obj_current = active_agent_instance._battles.get(battle_tag)

                    if battle_obj_current:
                        is_finished = battle_obj_current.finished
                        print(f"[{loop_counter}] State 2a: Battle object found. Finished: {is_finished}")
                        if not is_finished:
                            print(f"[{loop_counter}] State 2a: Battle {battle_tag} IN PROGRESS. Setting iframe HTML.")
                            # Every 3 cycles (based on loop_counter), regenerate the iframe HTML to ensure fresh content
                            if loop_counter % 3 == 0:
                                current_display_html = create_battle_iframe(battle_tag)
                                print(f"[{loop_counter}] Regenerated iframe HTML (periodic refresh)")
                            # Add check immediately after setting
                            if "iframe" not in current_display_html: print(f"[{loop_counter}] ***ERROR: IFRAME not found in generated HTML!***")

                        else:
                            print(f"[{loop_counter}] State 2a: Battle {battle_tag} FINISHED. Deactivating agent.")
                            await deactivate_current_agent(reason="battle_end")
                            await asyncio.sleep(5); continue
                    else:
                        print(f"[{loop_counter}] State 2a WARNING: Battle object for {battle_tag} MISSING! Deactivating.")
                        await deactivate_current_agent(reason="battle_object_missing"); continue

                # State 2b: Agent active, no battle (listening)
                else:
                    print(f"[{loop_counter}] State 2b: Agent {active_agent_name} LISTENING. Setting idle HTML.")
                    current_display_html = create_idle_html(f"Agent <strong>{active_agent_name}</strong> is ready!", f"Please challenge <strong>{active_agent_name}</strong> to a <strong>{DEFAULT_BATTLE_FORMAT}</strong> battle.")
                    if "is ready" not in current_display_html: print(f"[{loop_counter}] ***ERROR: IDLE text not found in generated HTML!***")

            # --- HTML Change Check ---
            new_html_start = current_display_html[:60]
            if new_html_start != previous_html_start:
                print(f"[{loop_counter}] HTML CHANGED! Type: {type(current_display_html)}, New HTML starts: {new_html_start}...")
            else:
                print(f"[{loop_counter}] HTML Unchanged. Starts: {new_html_start}...")
            # --- End HTML Change Check ---

            print(f"[{loop_counter}] State End. Sleeping {REFRESH_INTERVAL_SECONDS}s.")

        except Exception as e:
            print(f"ERROR in main lifecycle loop #{loop_counter}: {e}")
            traceback.print_exc()
            if active_agent_instance: await deactivate_current_agent(reason="main_loop_error")
            else: current_display_html = create_error_html(f"Error in lifecycle manager: {e}")
            await asyncio.sleep(10)

        await asyncio.sleep(REFRESH_INTERVAL_SECONDS)


# --- Gradio Update Function (Enhanced Logging) ---
def update_viewer_from_state():
    """Called by Gradio (triggered by JS click) to update the HTML component."""
    global current_display_html
    # Use a more unique identifier for the HTML content type
    html_indicator = "iframe" if "<iframe" in current_display_html[:100].lower() else "idle/other"
    
    # For iframe content, add a timestamp to force refresh
    if html_indicator == "iframe":
        # Extract the current URL from the iframe
        url_match = re.search(r'src="([^"]+)"', current_display_html)
        if url_match:
            original_url = url_match.group(1)
            # Update the timestamp in the URL
            updated_url = re.sub(r'cachebust=\d+', f'cachebust={int(time.time() * 1000)}', original_url)
            # Replace the URL in the iframe HTML
            current_display_html = current_display_html.replace(original_url, updated_url)
    
    print(f"Gradio Trigger [{time.strftime('%H:%M:%S')}]: Updating viewer. Current HTML type: {html_indicator}. Starts: {current_display_html[:100]}...")
    return gr.update(value=current_display_html)


async def start_background_tasks():
    """Creates and stores the background monitor task."""
    global background_task_handle
    if not background_task_handle or background_task_handle.done():
        print("Launching background lifecycle manager task...")
        # Start the new lifecycle manager task
        background_task_handle = asyncio.create_task(manage_agent_lifecycle(), name="lifecycle_manager")
        background_task_handle.add_done_callback(log_task_exception)
    else:
        print("Background lifecycle manager task already running.")

def log_task_exception(task: asyncio.Task):
    """Callback to log exceptions from background tasks."""
    try:
        if task.cancelled():
             print(f"Task {task.get_name()} was cancelled.")
             return
        task.result() # Raises exception if task failed
        print(f"Task {task.get_name()} finished cleanly.")
    except asyncio.CancelledError:
        # Logged above
        pass
    except Exception as e:
        print(f"Exception in background task {task.get_name()}: {e}")
        traceback.print_exc()
        # Potentially trigger a reset or error display state here
        # global current_display_html
        # current_display_html = create_error_html(f"Error in {task.get_name()}: {e}")

def main_app():
    print("Defining Gradio UI (Twitch Mode - Sequential Lifecycle)...")
    css = "body {padding: 0 !important; margin: 0 !important;} .gradio-container {max-width: none !important;}"

    with gr.Blocks(title="Pokemon Showdown Stream", css=css) as demo:
        viewer_html = gr.HTML(current_display_html)
        refresh_trigger_btn = gr.Button("Refresh Internally", visible=False, elem_id="refresh_trigger_btn_id")

        # JS click interval needs to be faster or equal to REFRESH_INTERVAL_SECONDS
        js_click_script = f"""
        <script>
        function triggerRefresh() {{
            var btn = document.getElementById('refresh_trigger_btn_id');
            if (btn) {{
                // console.log('JS: Clicking hidden refresh button'); // Reduce noise
                btn.click();
            }} else {{ console.error('JS: Could not find refresh button'); }}
            
            // Also try to directly refresh any iframes on the page
            const iframes = document.querySelectorAll('iframe');
            iframes.forEach(iframe => {{
                try {{
                    // Try to reload the iframe content
                    if (iframe.contentWindow) {{
                        // Add timestamp to src to force refresh
                        const currentSrc = iframe.src;
                        if (currentSrc && currentSrc.includes('cachebust=')) {{
                            const newSrc = currentSrc.replace(/cachebust=\\d+/, `cachebust=${{Date.now()}}`);
                            iframe.src = newSrc;
                        }}
                        // Also try to reload the content window
                        if (iframe.contentWindow.location) {{
                            iframe.contentWindow.location.reload(true);
                        }}
                    }}
                }} catch (e) {{
                    // Silently catch errors (might be cross-origin issues)
                }}
            }});
        }}
        const refreshInterval = setInterval(triggerRefresh, {int(REFRESH_INTERVAL_SECONDS * 1000)});
        </script>
        """
        _ = gr.Markdown(js_click_script, visible=False)

        # Event Handlers
        # 1. Start the background lifecycle manager task ONCE on load
        demo.load(start_background_tasks, inputs=None, outputs=None)
        # 2. When the hidden button is clicked (by JS), update the HTML viewer
        refresh_trigger_btn.click(update_viewer_from_state, inputs=None, outputs=viewer_html)

        print("Gradio UI defined. Background task and JS trigger configured.")
    return demo
# --- End Gradio UI ---

# --- Main execution block ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logging.getLogger('poke_env').setLevel(logging.WARNING)
    print("Starting application (Twitch Mode - Sequential Lifecycle)..."); print("="*50)

    if not AVAILABLE_AGENT_NAMES:
         print("FATAL: No agents found with configured passwords. Please set environment variables:")
         for name, cfg in AGENT_CONFIGS.items(): print(f"- {cfg.get('password_env_var', 'N/A')} (for agent: {name})")
         print("="*50)
         # Prevent Gradio from starting if no agents can run
         exit("Exiting due to missing agent passwords.")
    else:
         print("Found available agents:")
         for name in AVAILABLE_AGENT_NAMES: print(f"- {name}")
    print("="*50)

    app = main_app()
    print("Launching Gradio app...")

    try:
        app.queue().launch(share=False, server_name="0.0.0.0")
    finally:
        print("\nGradio app shut down.")
        print("Attempting to cancel tasks...")

        # --- Modified Cleanup for Sequential Model ---
        async def cleanup_tasks():
            global background_task_handle
            tasks_to_cancel = []
            agent_to_disconnect = active_agent_instance # Get current agent before potentially clearing state

            # Add main lifecycle manager task
            if background_task_handle and not background_task_handle.done():
                tasks_to_cancel.append(background_task_handle)
            # Add active agent's accept_challenges task if it exists and running
            if active_agent_task and not active_agent_task.done():
                 tasks_to_cancel.append(active_agent_task)

            if tasks_to_cancel:
                print(f"Sending cancel signal to {len(tasks_to_cancel)} tasks...")
                for task in tasks_to_cancel: task.cancel()
                results = await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
                print(f"Finished waiting for task cancellation. Results: {results}")

            # Attempt disconnect on the potentially active agent
            if agent_to_disconnect:
                 print(f"Attempting disconnect for last active agent {agent_to_disconnect.username}...")
                 if hasattr(agent_to_disconnect, 'disconnect') and callable(agent_to_disconnect.disconnect):
                     try:
                         if hasattr(agent_to_disconnect, '_websocket') and agent_to_disconnect._websocket and agent_to_disconnect._websocket.open:
                             await agent_to_disconnect.disconnect()
                             print(f"Agent {agent_to_disconnect.username} disconnected.")
                         else: print(f"Agent {agent_to_disconnect.username} already disconnected or websocket not ready.")
                     except Exception as e: print(f"Error during cleanup disconnect for {agent_to_disconnect.username}: {e}")
            else:
                 print("No active agent instance to disconnect during cleanup.")

            print("Cleanup attempt finished.")
        # --- End Modified Cleanup ---

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(cleanup_tasks())
            time.sleep(3) # Allow time for cleanup signals
        except RuntimeError:
             try: asyncio.run(cleanup_tasks())
             except Exception as e: print(f"Could not run final async cleanup: {e}")
        except Exception as e:
            print(f"An unexpected error occurred during cleanup: {e}")

        print("Application finished.")