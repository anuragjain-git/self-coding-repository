import os
import json
import openai
from pathlib import Path
import re
import logging
import subprocess
import traceback
from datetime import datetime
import html.parser
import cssutils
import esprima

class ProjectManager:
    def __init__(self):
        self.openai_api_key = os.getenv('OPENAI_API_KEY')
        self.project_root = Path('.')
        self.requirements_file = self.project_root / 'project_requirements.txt'

        # Setup logging
        self.setup_logging()
        
        # Initialize error checkers
        cssutils.log.setLevel(logging.CRITICAL)  # Suppress cssutils warnings
        self.html_parser = html.parser.HTMLParser()

    def chatgpt_generate(self, prompt):
        """Generates a response from ChatGPT API."""
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4",  # Use "gpt-3.5-turbo" if you want a cheaper option
                messages=[{"role": "system", "content": "You are an expert code assistant."},
                          {"role": "user", "content": prompt}],
                temperature=0.3
            )
            return response['choices'][0]['message']['content'].strip()
        except Exception as e:
            logging.error(f"Error generating content with ChatGPT: {str(e)}")
            return None

    def check_implementation(self, requirement):
        """Check if a requirement is implemented by analyzing existing files."""
        try:
            files_to_check = {
                'html': self.project_root / 'index.html',
                'css': self.project_root / 'styles.css',
                'js': self.project_root / 'script.js'
            }

            content = ''
            for file_path in files_to_check.values():
                if file_path.exists():
                    with open(file_path, 'r') as f:
                        content += f'\n' + f.read()

            if not content.strip():
                return False

            prompt = f"""
            Analyze if this requirement is implemented in the provided code:
            
            Requirement: {requirement}
            
            Code:
            {content}
            
            Respond with only 'YES' or 'NO'.
            """
            
            response = self.chatgpt_generate(prompt)
            return response.upper() == 'YES'
        except Exception as e:
            logging.error(f"Error checking implementation: {str(e)}")
            return False

    def implement_requirement(self, requirement):
        """Implement a new requirement using ChatGPT."""
        prompt = f"""
        Implement the following requirement for a web project:
        {requirement}

        Provide *only* the complete and necessary HTML, CSS, and JavaScript code to implement the feature, formatted as a JSON object:
        
        {{
            "html": "<HTML_CODE>",
            "css": "<CSS_CODE>",
            "js": "<JS_CODE>",
            "description": "<DESCRIPTION>"
        }}
        """
        
        response = self.chatgpt_generate(prompt)
        
        if response:
            try:
                implementation = json.loads(response)
                if implementation.get('html'):
                    self._update_file('index.html', implementation['html'])
                if implementation.get('css'):
                    self._update_file('styles.css', implementation['css'])
                if implementation.get('js'):
                    self._update_file('script.js', implementation['js'])
                self._update_readme(requirement, implementation.get('description', ''))
            except json.JSONDecodeError:
                logging.error("Invalid JSON response from ChatGPT")
        
    def run(self):
        """Main execution method."""
        logging.info("Starting project manager run")
        try:
            requirements = self.read_requirements()
            for requirement in requirements:
                if not self.check_implementation(requirement):
                    self.implement_requirement(requirement)
            logging.info("Completed project manager run")
        except Exception as e:
            logging.error(f"Error in main execution: {str(e)}\n{traceback.format_exc()}")

if __name__ == "__main__":
    openai.api_key = os.getenv("OPENAI_API_KEY")
    manager = ProjectManager()
    manager.run()
