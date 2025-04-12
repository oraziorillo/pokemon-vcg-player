toolsList=[
            {
                "name": "choose_move",
                "description": "Selects and executes an available attacking or status move.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "move_name": {
                            "type": "string",
                            "description": "The exact name of the move to use (e.g., 'Thunderbolt', 'Swords Dance'). Must be one of the available moves.",
                        },
                    },
                    "required": ["move_name"],
                },
            },
            {
                "name": "choose_switch",
                "description": "Selects an available Pokémon from the bench to switch into.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pokemon_name": {
                            "type": "string",
                            "description": "The exact name of the Pokémon species to switch to (e.g., 'Pikachu', 'Charizard'). Must be one of the available switches.",
                        },
                    },
                    "required": ["pokemon_name"],
                },
            },
        ]