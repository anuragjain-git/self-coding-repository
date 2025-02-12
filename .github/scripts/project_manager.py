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

    def read_requirements(self):
        """Read and parse project requirements from the requirements file."""
        try:
            with open(self.requirements_file, 'r') as f:
                requirements = []
                current_requirement = ""

                for line in f:
                    line = line.strip()
                    if not line:  # Ignore empty lines
                        continue

                    if line.startswith("-"):
                        current_requirement += f"\n{line}"
                    else:
                        if current_requirement:
                            requirements.append(current_requirement.strip())
                        current_requirement = line

                if current_requirement:  # Ensure the last requirement is added
                    requirements.append(current_requirement.strip())

            self.logger.info(f"Read {len(requirements)} requirements")
            return requirements

        except Exception as e:
            self.logger.error(f"Error reading requirements: {str(e)}")
            return []

    def setup_logging(self):
        """Sets up logging for the project."""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)

        fix_log_dir = log_dir / "fixes"
        fix_log_dir.mkdir(exist_ok=True)  # Ensure fix logs directory exists

        logging.basicConfig(
            filename=log_dir / "project_manager.log",
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s"
        )
        self.logger = logging.getLogger(__name__)
        self.logger.info("Logging initialized.")


    def chatgpt_generate(self, prompt):
        """Generates a response from OpenAI's Chat API."""
        try:
            client = openai.OpenAI(api_key=self.openai_api_key)  # Create a client
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",  # or "gpt-4"
                messages=[
                    {"role": "system", "content": "You are an expert code assistant."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            self.logger.error(f"Error generating content with ChatGPT: {str(e)}")
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
            self.logger.error(f"Error checking implementation: {str(e)}")
            return False

    
    def _update_file(self, filename, content):
        """Update or create a file with new content."""
        try:
            file_path = self.project_root / filename
            
            # Create file if it doesn't exist
            if not file_path.exists():
                file_path.touch()
                
            # Read existing content
            existing_content = ''
            if file_path.stat().st_size > 0:
                with open(file_path, 'r') as f:
                    existing_content = f.read()
            
            # Append new content if it's not already there
            if content.strip() not in existing_content:
                with open(file_path, 'a') as f:
                    f.write('\n' + content)
                    
            self.logger.info(f"Updated {filename}")
        
        except Exception as e:
            self.logger.error(f"Error updating {filename}: {str(e)}")

    def _update_readme(self, requirement, description):
        """Update README.md with new implementation details."""
        try:
            readme_path = self.project_root / 'README.md'

            # Ensure README exists
            if not readme_path.exists():
                content = "# Auto-Generated Project\n\n## Implemented Features\n\n"
            else:
                with open(readme_path, 'r') as f:
                    content = f.read()

            # Add "Implemented Features" section if missing
            if "## Implemented Features" not in content:
                content += "\n## Implemented Features\n\n"

            feature_entry = f"### {requirement}\n{description}\n\n"

            if feature_entry not in content:
                content += feature_entry
                with open(readme_path, 'w') as f:
                    f.write(content)

            self.logger.info(f"Updated README.md with requirement: {requirement}")

        except Exception as e:
            self.logger.error(f"Error updating README: {str(e)}")


    def check_html_errors(self, content):
        """Check HTML for syntax errors"""
        try:
            self.html_parser.feed(content)
            return None
        except Exception as e:
            return str(e)

    def check_css_errors(self, content):
        """Check CSS for syntax errors"""
        try:
            cssutils.parseString(content)
            return None
        except Exception as e:
            return str(e)

    def check_js_errors(self, content):
        """Check JavaScript for syntax errors"""
        try:
            esprima.parseScript(content)
            return None
        except Exception as e:
            return str(e)

    def fix_code_error(self, code, error, language):
        """Use ChatGPT to fix code errors"""
        prompt = f"""
        Fix the following {language} code that has this error:
        Error: {error}
        
        Code:
        {code}
        
        Provide only the fixed code without any explanations.
        """
        
        try:
            response = self.chatgpt_generate(prompt)
            fixed_code = response.strip() if response else None
            
            # Verify the fix worked
            if language == 'HTML':
                new_error = self.check_html_errors(fixed_code)
            elif language == 'CSS':
                new_error = self.check_css_errors(fixed_code)
            elif language == 'JavaScript':
                new_error = self.check_js_errors(fixed_code)
            else:
                self.logger.error(f"Unsupported language: {language}")
                return None
                
            if new_error:
                self.logger.error(f"Fix attempt failed. New error: {new_error}")
                return None
                
            return fixed_code
            
        except Exception as e:
            self.logger.error(f"Error during fix attempt: {str(e)}")
            return None
        
    def log_fix(self, file_path, error, original_content, fixed_content):
        """Logs the fixes applied to a file."""
        fix_log_path = self.project_root / "logs/fixes" / f"{file_path.name}.fix.log"
        os.makedirs(fix_log_path.parent, exist_ok=True)
        with open(fix_log_path, "a") as f:
            f.write(f"\n{datetime.now()} - Fix applied to {file_path}\n")
            f.write(f"Original Error: {error}\n")
            f.write(f"Original Content:\n{original_content}\n")
            f.write(f"Fixed Content:\n{fixed_content}\n")

        
    def check_and_fix_file(self, file_path):
        """Check a file for errors and fix if necessary"""
        with open(file_path, 'r') as f:
            content = f.read()
            
        file_type = file_path.suffix.lower()
        error = None
        
        if file_type == '.html':
            error = self.check_html_errors(content)
            language = 'HTML'
        elif file_type == '.css':
            error = self.check_css_errors(content)
            language = 'CSS'
        elif file_type == '.js':
            error = self.check_js_errors(content)
            language = 'JavaScript'
        else:
            return
            
        if error:
            self.logging.warning(f"Found error in {file_path}: {error}")
            fixed_code = self.fix_code_error(content, error, language)
            
            if fixed_code:
                # Backup original file
                backup_path = file_path.with_suffix(f"{file_path.suffix}.backup")
                with open(backup_path, 'w') as f:
                    f.write(content)
                    
                # Write fixed code
                with open(file_path, 'w') as f:
                    f.write(fixed_code)
                    
                self.logger.info(f"Fixed error in {file_path}. Original backed up to {backup_path}")
                
                # Log the fix details
                self.log_fix(file_path, error, content, fixed_code)

    
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
            
                # Check for errors in updated files
                for file_name in ['index.html', 'styles.css', 'script.js']:
                    file_path = self.project_root / file_name
                    if file_path.exists():
                        self.check_and_fix_file(file_path)
                
                # Update README
                self._update_readme(requirement, implementation['description'])
            
            except json.JSONDecodeError:
                self.logger.error("Invalid JSON response from ChatGPT")
        
    def run(self):
        """Main execution method."""
        self.logger.info("Starting project manager run")
        try:
            if not self.requirements_file.exists():
                self.logger.warning("No project_requirements.txt file found, skipping requirement parsing.")
                return  # Exit early if no requirements file
            
            requirements = self.read_requirements()
            for requirement in requirements:
                self.logger.info(f"Processing requirement: {requirement}")
                if not self.check_implementation(requirement):
                    self.logger.info(f"Implementing requirement: {requirement}")
                    self.implement_requirement(requirement)
                else:
                    self.logger.info(f"Requirement already implemented: {requirement}")

                        # Check all existing files for errors
            for file_type in ['.html', '.css', '.js']:
                for file_path in self.project_root.rglob(f'*{file_type}'):
                    self.check_and_fix_file(file_path)

        except Exception as e:
            self.logger.error(f"Error in main execution: {str(e)}\n{traceback.format_exc()}")
        
        self.logger.info("Completed project manager run")

if __name__ == "__main__":
    openai.api_key = os.getenv("OPENAI_API_KEY")
    manager = ProjectManager()
    manager.run()
