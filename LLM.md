Instructions for LLMs
- Avoid being overtly verbose in chat if you are not requesting user input to save tokens.
- Keep config.example.yaml up to date
- Avoid creating huge code files.
- Token optimization: Button update logic is centralized in `src/deckky/button_utils.py` - use it when modifying button update functions.
