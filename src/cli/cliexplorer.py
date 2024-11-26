import subprocess
import re
import json
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import argparse

@dataclass
class Parameter:
    name: str
    description: str
    type: Optional[str] = None
    required: bool = False
    default: Optional[str] = None
    choices: Optional[List[str]] = None

@dataclass
class Command:
    name: str
    description: str
    parameters: List[Parameter]
    subcommands: Dict[str, 'Command']

class CLIExplorer:
    def __init__(self, base_command: str):
        """Initialize the CLI explorer with the base command to analyze."""
        self.base_command = base_command
        self.visited_commands = set()  # Track visited commands to avoid cycles

    def _execute_help_command(self, command_parts: List[str]) -> str:
        """Execute a help command and return its output."""
        try:
            # Try with --help first
            result = subprocess.run(
                command_parts + ["--help"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return result.stdout
            
            # Fall back to -h if --help fails
            result = subprocess.run(
                command_parts + ["-h"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.stdout
        except subprocess.TimeoutExpired:
            print(f"Command timed out: {' '.join(command_parts)}")
            return ""
        except subprocess.SubprocessError as e:
            print(f"Error executing command {' '.join(command_parts)}: {e}")
            return ""

    def _parse_parameters(self, help_text: str) -> List[Parameter]:
        """Parse parameters from help text output."""
        parameters = []
        
        # First try to parse usage pattern for git-style commands
        usage_match = re.search(r'usage:.*?\n((?:.*\n)*?)(?:\n|$)', help_text, re.IGNORECASE)
        if usage_match:
            usage_lines = usage_match.group(1).strip().split('\n')
            for line in usage_lines:
                # Parse git-style parameter patterns: [-v | --version] [-C <path>] etc.
                param_matches = re.finditer(r'\[(?:-([a-zA-Z])\s*\|?\s*)?(?:--([a-zA-Z0-9-]+))(?:(?:[=\s])?(?:<([^>]+)>))?\]', line)
                for match in param_matches:
                    short_opt, long_opt, param_type = match.groups()
                    name = long_opt or short_opt
                    if name:
                        parameters.append(Parameter(
                            name=name,
                            description=f"Option from usage pattern{f' (takes {param_type})' if param_type else ''}",
                            type=param_type,
                            required=False
                        ))

        # Then parse detailed option descriptions
        # Common patterns for argument descriptions
        param_patterns = [
            # GNU style: --param-name, -p PARAM description
            r'(?:(-[a-zA-Z]),\s+)?(--[a-zA-Z0-9-]+)(?:\s+([A-Z_]+))?\s+(.+?)(?=(?:\n\s+(?:-|$)|\n\n|\Z))',
            # Simple style: -p, --param-name description
            r'(?:(-[a-zA-Z]),\s+)?(--[a-zA-Z0-9-]+)\s+(.+?)(?=(?:\n\s+(?:-|$)|\n\n|\Z))',
            # Git style options section
            r'^\s+(-[a-zA-Z]|\-\-[a-zA-Z0-9-]+)(?:\s*[=\s]\s*<([^>]+)>)?\s+(.+?)(?=\n\s+(?:-|$)|\n\n|\Z)',
        ]

        for pattern in param_patterns:
            matches = re.finditer(pattern, help_text, re.MULTILINE)
            for match in matches:
                groups = match.groups()
                
                if len(groups) == 4:  # GNU style with type
                    short_name, long_name, param_type, description = groups
                elif len(groups) == 3:  # Simple style
                    short_name, long_name, description = groups
                    param_type = None
                else:
                    continue

                # Clean up parameter name
                name = (long_name or short_name).lstrip('-')
                
                # Parse additional metadata from description
                required = any(word in description.lower() 
                             for word in ['required', 'mandatory'])
                
                # Look for default values
                default_match = re.search(r'default[: ]+([^)\n]+)', 
                                        description, re.IGNORECASE)
                default = default_match.group(1) if default_match else None

                # Look for choices
                choices_match = re.search(r'(?:choices|options)[: ]+\{([^}]+)\}', 
                                       description, re.IGNORECASE)
                choices = [c.strip() for c in choices_match.group(1).split(',')
                          ] if choices_match else None

                param = Parameter(
                    name=name,
                    description=description.strip(),
                    type=param_type,
                    required=required,
                    default=default,
                    choices=choices
                )
                parameters.append(param)

        return parameters

    def _extract_subcommands(self, help_text: str) -> List[str]:
        """Extract subcommands from help text output."""
        subcommands = []
        
        # Common patterns for subcommand sections
        section_patterns = [
            r'(?:Commands|Subcommands):\n((?:\s+\w+.*\n)+)',
            r'available\s+commands:\n((?:\s+\w+.*\n)+)',
        ]

        for pattern in section_patterns:
            section_match = re.search(pattern, help_text, re.IGNORECASE)
            if section_match:
                section = section_match.group(1)
                # Extract command names from the section
                command_matches = re.finditer(r'\s+(\w+)[:\s]', section)
                subcommands.extend(match.group(1) for match in command_matches)

        return subcommands

    def explore_command(self, command_parts: List[str]) -> Command:
        """
        Recursively explore a command and its subcommands.
        
        Args:
            command_parts: List of command parts (e.g., ['git', 'remote', 'add'])
            
        Returns:
            Command object representing the command structure
        """
        # Create command identifier for cycle detection
        command_id = ' '.join(command_parts)
        if command_id in self.visited_commands:
            return Command(
                name=command_parts[-1],
                description="[Circular reference]",
                parameters=[],
                subcommands={}
            )
        
        self.visited_commands.add(command_id)
        
        # Get help text for current command
        help_text = self._execute_help_command(command_parts)
        if not help_text:
            return Command(
                name=command_parts[-1],
                description="[No help text available]",
                parameters=[],
                subcommands={}
            )

        # Extract command description, looking for a proper description beyond usage
        description = ""
        paragraphs = help_text.split('\n\n')
        
        # Skip usage paragraphs and find the first real description
        for para in paragraphs:
            para = para.strip()
            # Skip usage patterns, empty lines, and common non-description sections
            if (not para.lower().startswith('usage:') and 
                not para.lower().startswith('these are common git commands') and
                not all(c in '-=_' for c in para) and  # Skip separator lines
                len(para) > 0):
                description = para
                break
        
        if not description:
            # Fallback to first non-empty paragraph if no clear description found
            description = next((p.strip() for p in paragraphs if p.strip()), "")
        
        # Parse parameters
        parameters = self._parse_parameters(help_text)
        
        # Get subcommands
        subcommands_list = self._extract_subcommands(help_text)
        
        # Recursively explore subcommands
        subcommands = {}
        for subcmd in subcommands_list:
            new_command_parts = command_parts + [subcmd]
            subcommands[subcmd] = self.explore_command(new_command_parts)
            
        return Command(
            name=command_parts[-1],
            description=description,
            parameters=parameters,
            subcommands=subcommands
        )

    def generate_schema(self) -> Dict:
        """Generate a complete schema for the CLI command."""
        command_structure = self.explore_command([self.base_command])
        
        # Convert to dictionary and clean up for JSON output
        def _clean_dict(d):
            if isinstance(d, (Command, Parameter)):
                d = asdict(d)
            if isinstance(d, dict):
                return {k: _clean_dict(v) for k, v in d.items() 
                        if v is not None and v != [] and v != {}}
            if isinstance(d, list):
                return [_clean_dict(i) for i in d]
            return d
            
        return _clean_dict(command_structure)

def main():
    parser = argparse.ArgumentParser(
        description='Explore and document CLI command structure')
    parser.add_argument('command', help='Base command to explore')
    parser.add_argument('--output', '-o', help='Output JSON file path')
    args = parser.parse_args()

    explorer = CLIExplorer(args.command)
    schema = explorer.generate_schema()
    
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(schema, f, indent=2)
    else:
        print(json.dumps(schema, indent=2))

if __name__ == '__main__':
    main()
