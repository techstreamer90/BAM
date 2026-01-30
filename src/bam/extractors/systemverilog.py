"""
SystemVerilog Extractor

Extracts structural information from SystemVerilog (.sv) and Verilog (.v) files.
Uses regex-based parsing to identify modules, interfaces, packages, classes,
and their relationships.
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Tuple

from .base import BaseExtractor, ExtractionResult


logger = logging.getLogger("bam.extractors.systemverilog")


@dataclass
class SVEntity:
    """Represents a SystemVerilog entity (module, interface, package, class)."""
    entity_type: str  # module, interface, package, class
    name: str
    file_path: str
    line_number: int
    parameters: List[Dict[str, str]] = field(default_factory=list)
    ports: List[Dict[str, str]] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    includes: List[str] = field(default_factory=list)
    extends: Optional[str] = None  # For classes
    instantiates: List[Dict[str, str]] = field(default_factory=list)
    functions: List[str] = field(default_factory=list)
    tasks: List[str] = field(default_factory=list)
    description: Optional[str] = None
    # Agent-helpful classifications
    category: Optional[str] = None  # "rtl", "verification", "package"
    role: Optional[str] = None  # For verification: "test", "env", "agent", etc.


class SystemVerilogExtractor(BaseExtractor):
    """Extractor for SystemVerilog and Verilog files."""

    EXTRACTOR_TYPE = "systemverilog"
    FILE_EXTENSIONS = ["sv", "v", "svh", "vh"]

    # Regex patterns for parsing
    # These handle common cases; complex macros/generates may need manual review

    # Module: module name import pkg::*; #(params) (ports);
    MODULE_PATTERN = re.compile(
        r'^\s*module\s+(\w+)\s*'
        r'(?:import\s+[\w:*,\s]+;\s*)?'  # Optional imports
        r'(?:#\s*\([^)]*\))?\s*'          # Optional parameters
        r'(?:\([^)]*\))?\s*;',             # Optional ports
        re.MULTILINE
    )

    # Interface: interface name #(params) (ports);
    INTERFACE_PATTERN = re.compile(
        r'^\s*interface\s+(\w+)\s*'
        r'(?:#\s*\([^)]*\))?\s*'  # Optional parameters
        r'(?:\([^)]*\))?\s*;',     # Optional ports
        re.MULTILINE
    )

    # Package: package name;
    PACKAGE_PATTERN = re.compile(
        r'^\s*package\s+(\w+)\s*;',
        re.MULTILINE
    )

    # Class: class name extends parent;
    CLASS_PATTERN = re.compile(
        r'^\s*(?:virtual\s+)?class\s+(\w+)\s*'
        r'(?:extends\s+(\w+))?\s*;',
        re.MULTILINE
    )

    # Function: function [type] name
    FUNCTION_PATTERN = re.compile(
        r'^\s*(?:virtual\s+)?function\s+(?:automatic\s+)?'
        r'(?:[\w\[\]:]+\s+)?'  # Return type
        r'(\w+)\s*[;(]',
        re.MULTILINE
    )

    # Task: task [automatic] name
    TASK_PATTERN = re.compile(
        r'^\s*(?:virtual\s+)?task\s+(?:automatic\s+)?(\w+)\s*[;(]',
        re.MULTILINE
    )

    # Import: import pkg::item; or import pkg::*;
    IMPORT_PATTERN = re.compile(
        r'^\s*import\s+([\w:*]+)\s*;',
        re.MULTILINE
    )

    # Include: `include "file"
    INCLUDE_PATTERN = re.compile(
        r'^\s*`include\s+["\']([^"\']+)["\']',
        re.MULTILINE
    )

    # Module instantiation: module_name #(.param(val)) instance_name (
    # This is tricky - we look for identifier followed by optional params and instance name
    INSTANTIATION_PATTERN = re.compile(
        r'^\s*(\w+)\s*'                    # Module type
        r'(?:#\s*\([^)]*\)\s*)?'           # Optional parameters
        r'(\w+)\s*'                         # Instance name
        r'\(',                              # Port list start
        re.MULTILINE
    )

    # Parameter declaration (simplified)
    PARAMETER_DECL_PATTERN = re.compile(
        r'parameter\s+(?:\w+\s+)?(\w+)\s*=\s*([^,;)]+)',
        re.MULTILINE
    )

    # Port declaration patterns
    PORT_INPUT_PATTERN = re.compile(
        r'input\s+(?:wire\s+|logic\s+|reg\s+)?(?:\[[^\]]+\]\s*)?(\w+)',
        re.MULTILINE
    )
    PORT_OUTPUT_PATTERN = re.compile(
        r'output\s+(?:wire\s+|logic\s+|reg\s+)?(?:\[[^\]]+\]\s*)?(\w+)',
        re.MULTILINE
    )
    PORT_INOUT_PATTERN = re.compile(
        r'inout\s+(?:wire\s+|logic\s+|reg\s+)?(?:\[[^\]]+\]\s*)?(\w+)',
        re.MULTILINE
    )

    # Keywords that look like module names but aren't (for filtering instantiations)
    SV_KEYWORDS = {
        'if', 'else', 'begin', 'end', 'case', 'endcase', 'for', 'while',
        'always', 'always_ff', 'always_comb', 'always_latch', 'initial',
        'assign', 'wire', 'reg', 'logic', 'input', 'output', 'inout',
        'parameter', 'localparam', 'genvar', 'generate', 'endgenerate',
        'function', 'endfunction', 'task', 'endtask', 'return',
        'module', 'endmodule', 'interface', 'endinterface',
        'package', 'endpackage', 'class', 'endclass',
        'typedef', 'struct', 'enum', 'union', 'packed',
        'assert', 'assume', 'cover', 'property', 'sequence',
        'clocking', 'endclocking', 'default', 'disable', 'fork', 'join',
        'posedge', 'negedge', 'or', 'and', 'not', 'xor',
        'integer', 'real', 'time', 'bit', 'byte', 'shortint', 'int', 'longint',
        'void', 'string', 'chandle', 'virtual', 'static', 'automatic',
        'const', 'ref', 'var', 'new', 'null', 'this', 'super',
        'import', 'export', 'extern', 'context', 'pure',
        'unique', 'unique0', 'priority',  # case modifiers
        'casex', 'casez', 'inside', 'matches', 'tagged',
        'forever', 'repeat', 'do', 'break', 'continue',
        'wait', 'wait_order', 'expect', 'randcase',
    }

    # Common primitive types that look like instantiations
    SV_PRIMITIVES = {
        'and', 'nand', 'or', 'nor', 'xor', 'xnor', 'not', 'buf',
        'bufif0', 'bufif1', 'notif0', 'notif1',
        'pmos', 'nmos', 'cmos', 'rpmos', 'rnmos', 'rcmos',
        'tran', 'tranif0', 'tranif1', 'rtran', 'rtranif0', 'rtranif1',
        'pullup', 'pulldown',
    }

    # UVM base class patterns for role detection
    UVM_ROLE_PATTERNS = {
        # Exact matches
        'uvm_test': 'test',
        'uvm_env': 'env',
        'uvm_agent': 'agent',
        'uvm_driver': 'driver',
        'uvm_monitor': 'monitor',
        'uvm_scoreboard': 'scoreboard',
        'uvm_subscriber': 'subscriber',
        'uvm_sequencer': 'sequencer',
        'uvm_sequence': 'sequence',
        'uvm_sequence_item': 'sequence_item',
        'uvm_object': 'object',
        'uvm_component': 'component',
        # Common project patterns
        'dv_base_test': 'test',
        'dv_base_env': 'env',
        'dv_base_agent': 'agent',
        'dv_base_driver': 'driver',
        'dv_base_monitor': 'monitor',
        'dv_base_scoreboard': 'scoreboard',
        'dv_base_vseq': 'sequence',
        'dv_base_seq': 'sequence',
    }

    # Directory patterns suggesting verification code
    VERIF_DIR_PATTERNS = {'dv', 'tb', 'test', 'testbench', 'verif', 'verification', 'uvm', 'sim'}

    # Directory patterns suggesting RTL code
    RTL_DIR_PATTERNS = {'rtl', 'src', 'hdl', 'design', 'ip', 'core'}

    # Words that commonly appear as false positives (macros, labels, etc.)
    SV_FALSE_POSITIVES = {
        # From preprocessor directives (after ` is stripped)
        'define', 'undef', 'ifdef', 'ifndef', 'elsif', 'endif', 'include',
        'timescale', 'resetall', 'celldefine', 'endcelldefine',
        # Common label/state prefixes
        'IDLE', 'INIT', 'RESET', 'DONE', 'ERROR', 'READY', 'VALID',
        'START', 'STOP', 'WAIT', 'BUSY', 'FAIL', 'PASS',
        # Enum-like single words (often ALL_CAPS)
        'TRUE', 'FALSE', 'YES', 'NO', 'ON', 'OFF',
        # UVM macros
        'uvm_info', 'uvm_warning', 'uvm_error', 'uvm_fatal',
        'uvm_component_utils', 'uvm_object_utils', 'uvm_field_int',
    }

    def __init__(self, source_id: str, project_dir: Optional[str] = None):
        super().__init__(source_id, project_dir)
        self._known_modules: Dict[str, str] = {}  # name -> file path

    def extract_file(self, file_path: Path) -> Dict[str, Any]:
        """Extract structured data from a SystemVerilog file.

        Args:
            file_path: Path to the .sv or .v file.

        Returns:
            Dictionary with 'items' and 'relationships' lists.
        """
        file_path = Path(file_path)
        result = {
            "items": [],
            "relationships": [],
            "warnings": []
        }

        try:
            content = file_path.read_text(encoding='utf-8', errors='replace')
        except Exception as e:
            result["warnings"].append(f"Could not read {file_path}: {e}")
            return result

        # Remove comments for cleaner parsing
        clean_content = self._remove_comments(content)

        # Extract description from file header comment
        file_description = self._extract_header_comment(content)

        # Extract all entity types
        rel_path = str(file_path)

        # Modules
        for match in self.MODULE_PATTERN.finditer(clean_content):
            module_name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            entity = self._extract_module_details(
                clean_content, module_name, rel_path, line_num, file_description
            )
            result["items"].append(self._entity_to_item(entity))
            self._known_modules[module_name] = rel_path

            # Add relationships for instantiations
            for inst in entity.instantiates:
                result["relationships"].append({
                    "type": "INSTANTIATES",
                    "source": module_name,
                    "target": inst["module"],
                    "instance_name": inst["instance"],
                    "file": rel_path
                })

            # Add relationships for imports
            for imp in entity.imports:
                pkg_name = imp.split("::")[0]
                result["relationships"].append({
                    "type": "IMPORTS",
                    "source": module_name,
                    "target": pkg_name,
                    "file": rel_path
                })

        # Interfaces
        for match in self.INTERFACE_PATTERN.finditer(clean_content):
            iface_name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            entity = self._extract_interface_details(
                clean_content, iface_name, rel_path, line_num
            )
            result["items"].append(self._entity_to_item(entity))

        # Packages
        for match in self.PACKAGE_PATTERN.finditer(clean_content):
            pkg_name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            entity = self._extract_package_details(
                clean_content, pkg_name, rel_path, line_num
            )
            result["items"].append(self._entity_to_item(entity))

        # Classes
        for match in self.CLASS_PATTERN.finditer(clean_content):
            class_name = match.group(1)
            parent_class = match.group(2)
            line_num = content[:match.start()].count('\n') + 1
            entity = self._extract_class_details(
                clean_content, class_name, parent_class, rel_path, line_num
            )
            result["items"].append(self._entity_to_item(entity))

            # Add inheritance relationship
            if parent_class:
                result["relationships"].append({
                    "type": "EXTENDS",
                    "source": class_name,
                    "target": parent_class,
                    "file": rel_path
                })

        return result

    def _remove_comments(self, content: str) -> str:
        """Remove single-line and multi-line comments."""
        # Remove multi-line comments /* ... */
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        # Remove single-line comments // ...
        content = re.sub(r'//.*$', '', content, flags=re.MULTILINE)
        return content

    def _extract_header_comment(self, content: str) -> Optional[str]:
        """Extract description from file header comment block."""
        # Look for /** ... */ style doc comment at start
        match = re.match(r'^\s*(?://[^\n]*\n)*\s*/\*\*([^*]|\*[^/])*\*/', content)
        if match:
            comment = match.group(0)
            # Clean up the comment
            lines = comment.split('\n')
            desc_lines = []
            for line in lines:
                line = re.sub(r'^\s*[/*]*\s*', '', line)
                line = re.sub(r'\s*\*+/?\s*$', '', line)
                if line and not line.startswith(('Copyright', 'Licensed', 'SPDX')):
                    desc_lines.append(line)
            if desc_lines:
                return ' '.join(desc_lines).strip()
        return None

    def _extract_module_details(
        self,
        content: str,
        module_name: str,
        file_path: str,
        line_number: int,
        description: Optional[str]
    ) -> SVEntity:
        """Extract detailed information about a module."""
        entity = SVEntity(
            entity_type="module",
            name=module_name,
            file_path=file_path,
            line_number=line_number,
            description=description
        )

        # Find module body
        module_body = self._extract_entity_body(content, 'module', module_name)
        if not module_body:
            return entity

        # Extract parameters
        for match in self.PARAMETER_DECL_PATTERN.finditer(module_body):
            entity.parameters.append({
                "name": match.group(1),
                "default": match.group(2).strip()
            })

        # Extract ports
        for match in self.PORT_INPUT_PATTERN.finditer(module_body):
            entity.ports.append({"name": match.group(1), "direction": "input"})
        for match in self.PORT_OUTPUT_PATTERN.finditer(module_body):
            entity.ports.append({"name": match.group(1), "direction": "output"})
        for match in self.PORT_INOUT_PATTERN.finditer(module_body):
            entity.ports.append({"name": match.group(1), "direction": "inout"})

        # Extract imports
        for match in self.IMPORT_PATTERN.finditer(module_body):
            entity.imports.append(match.group(1))

        # Extract includes (from original content to preserve line info)
        for match in self.INCLUDE_PATTERN.finditer(content):
            entity.includes.append(match.group(1))

        # Extract instantiations
        entity.instantiates = self._extract_instantiations(module_body)

        # Extract functions and tasks
        for match in self.FUNCTION_PATTERN.finditer(module_body):
            func_name = match.group(1)
            if func_name not in self.SV_KEYWORDS:
                entity.functions.append(func_name)

        for match in self.TASK_PATTERN.finditer(module_body):
            task_name = match.group(1)
            if task_name not in self.SV_KEYWORDS:
                entity.tasks.append(task_name)

        return entity

    def _extract_interface_details(
        self,
        content: str,
        iface_name: str,
        file_path: str,
        line_number: int
    ) -> SVEntity:
        """Extract detailed information about an interface."""
        entity = SVEntity(
            entity_type="interface",
            name=iface_name,
            file_path=file_path,
            line_number=line_number
        )

        iface_body = self._extract_entity_body(content, 'interface', iface_name)
        if not iface_body:
            return entity

        # Extract parameters
        for match in self.PARAMETER_DECL_PATTERN.finditer(iface_body):
            entity.parameters.append({
                "name": match.group(1),
                "default": match.group(2).strip()
            })

        # Extract tasks (interfaces often have modports and tasks)
        for match in self.TASK_PATTERN.finditer(iface_body):
            task_name = match.group(1)
            if task_name not in self.SV_KEYWORDS:
                entity.tasks.append(task_name)

        return entity

    def _extract_package_details(
        self,
        content: str,
        pkg_name: str,
        file_path: str,
        line_number: int
    ) -> SVEntity:
        """Extract detailed information about a package."""
        entity = SVEntity(
            entity_type="package",
            name=pkg_name,
            file_path=file_path,
            line_number=line_number
        )

        pkg_body = self._extract_entity_body(content, 'package', pkg_name)
        if not pkg_body:
            return entity

        # Extract functions
        for match in self.FUNCTION_PATTERN.finditer(pkg_body):
            func_name = match.group(1)
            if func_name not in self.SV_KEYWORDS:
                entity.functions.append(func_name)

        # Extract imports (packages can import other packages)
        for match in self.IMPORT_PATTERN.finditer(pkg_body):
            entity.imports.append(match.group(1))

        return entity

    def _extract_class_details(
        self,
        content: str,
        class_name: str,
        parent_class: Optional[str],
        file_path: str,
        line_number: int
    ) -> SVEntity:
        """Extract detailed information about a class."""
        entity = SVEntity(
            entity_type="class",
            name=class_name,
            file_path=file_path,
            line_number=line_number,
            extends=parent_class
        )

        class_body = self._extract_entity_body(content, 'class', class_name)
        if not class_body:
            return entity

        # Extract functions
        for match in self.FUNCTION_PATTERN.finditer(class_body):
            func_name = match.group(1)
            if func_name not in self.SV_KEYWORDS:
                entity.functions.append(func_name)

        # Extract tasks
        for match in self.TASK_PATTERN.finditer(class_body):
            task_name = match.group(1)
            if task_name not in self.SV_KEYWORDS:
                entity.tasks.append(task_name)

        return entity

    def _extract_entity_body(
        self,
        content: str,
        entity_type: str,
        entity_name: str
    ) -> Optional[str]:
        """Extract the body of an entity (module, interface, package, class)."""
        # Find the start of the entity
        start_pattern = re.compile(
            rf'^\s*(?:virtual\s+)?{entity_type}\s+{re.escape(entity_name)}\b',
            re.MULTILINE
        )
        match = start_pattern.search(content)
        if not match:
            return None

        start_pos = match.start()
        end_keyword = f'end{entity_type}'

        # Simple nesting counter for begin/end blocks
        # This is a simplified approach; complex generates may confuse it
        pos = content.find(';', start_pos)  # Skip past declaration
        if pos == -1:
            return None

        # Find the matching end keyword
        depth = 1
        search_pos = pos + 1
        entity_pattern = re.compile(
            rf'\b({entity_type}|end{entity_type})\b'
        )

        while depth > 0 and search_pos < len(content):
            match = entity_pattern.search(content, search_pos)
            if not match:
                break
            if match.group(1) == entity_type:
                depth += 1
            else:
                depth -= 1
            search_pos = match.end()

        if depth == 0:
            return content[start_pos:search_pos]
        return content[start_pos:]

    def _extract_instantiations(self, module_body: str) -> List[Dict[str, str]]:
        """Extract module instantiations from a module body.

        Handles two common patterns:
        1. Simple: module_type instance_name (...);
        2. With params: module_type #(...) instance_name (...);

        The challenge is that parameters and ports can span many lines.
        """
        instantiations = []
        seen = set()  # Avoid duplicates

        def is_likely_module_name(name: str) -> bool:
            """Heuristic to determine if a name looks like a module name."""
            # Skip obvious non-modules
            if name in self.SV_KEYWORDS:
                return False
            if name in self.SV_PRIMITIVES:
                return False
            if name in self.SV_FALSE_POSITIVES:
                return False
            if name.startswith('$'):
                return False

            # ALL_CAPS names are usually constants/enums, not modules
            if name.isupper() and '_' not in name:
                return False

            # Single short words are often false positives
            if len(name) <= 3 and '_' not in name:
                return False

            # Names starting with capital that have no underscore are
            # often enum values or state names (e.g., "Illegal", "Ready")
            if name[0].isupper() and '_' not in name and not name.isupper():
                return False

            return True

        # Pattern 1: module_type #( ... ) instance_name (
        # This handles multi-line parameter blocks
        param_inst_pattern = re.compile(
            r'\b([A-Za-z_]\w*)\s*#\s*\(',  # module_type #(
            re.MULTILINE
        )

        for match in param_inst_pattern.finditer(module_body):
            module_type = match.group(1)

            if not is_likely_module_name(module_type):
                continue

            # Find the matching closing paren for params, then the instance name
            start = match.end()
            depth = 1
            pos = start

            while depth > 0 and pos < len(module_body):
                if module_body[pos] == '(':
                    depth += 1
                elif module_body[pos] == ')':
                    depth -= 1
                pos += 1

            if depth == 0:
                # Now look for instance_name (
                remainder = module_body[pos:pos+200]  # Look ahead
                inst_match = re.match(r'\s*(\w+)\s*\(', remainder)
                if inst_match:
                    instance_name = inst_match.group(1)
                    if instance_name not in self.SV_KEYWORDS:
                        key = (module_type, instance_name)
                        if key not in seen:
                            seen.add(key)
                            instantiations.append({
                                "module": module_type,
                                "instance": instance_name
                            })

        # Pattern 2: Simple instantiation without parameters
        # module_type instance_name ( ... );
        # Must not be preceded by # (which would be caught above)
        simple_pattern = re.compile(
            r'(?<![#\w])\b([A-Za-z_]\w*)\s+([A-Za-z_]\w*)\s*\(',
            re.MULTILINE
        )

        for match in simple_pattern.finditer(module_body):
            module_type = match.group(1)
            instance_name = match.group(2)

            if not is_likely_module_name(module_type):
                continue
            if instance_name in self.SV_KEYWORDS:
                continue

            key = (module_type, instance_name)
            if key not in seen:
                seen.add(key)
                instantiations.append({
                    "module": module_type,
                    "instance": instance_name
                })

        return instantiations

    def _classify_entity(self, entity: SVEntity) -> Tuple[Optional[str], Optional[str]]:
        """Classify an entity into category and role.

        Returns:
            Tuple of (category, role) where:
            - category: "rtl", "verification", or "package"
            - role: UVM component role like "test", "driver", etc. (for verification only)
        """
        category = None
        role = None

        # Packages are their own category
        if entity.entity_type == 'package':
            return ('package', None)

        # Check directory patterns for category hints
        path_lower = entity.file_path.lower().replace('\\', '/')
        path_parts = set(path_lower.split('/'))

        is_verif_path = bool(path_parts & self.VERIF_DIR_PATTERNS)
        is_rtl_path = bool(path_parts & self.RTL_DIR_PATTERNS)

        # Classes are almost always verification
        if entity.entity_type == 'class':
            category = 'verification'

            # Detect UVM role from extends chain
            if entity.extends:
                extends_lower = entity.extends.lower()

                # Check exact matches first
                if entity.extends in self.UVM_ROLE_PATTERNS:
                    role = self.UVM_ROLE_PATTERNS[entity.extends]
                else:
                    # Check suffix patterns
                    for pattern, r in self.UVM_ROLE_PATTERNS.items():
                        if extends_lower.endswith(pattern.replace('uvm_', '').replace('dv_base_', '')):
                            role = r
                            break

                    # Fallback: check if extends name contains role hint
                    if not role:
                        for hint in ['test', 'env', 'agent', 'driver', 'monitor',
                                     'scoreboard', 'sequencer', 'seq', 'item']:
                            if hint in extends_lower:
                                role = 'sequence' if hint == 'seq' else hint
                                break

        # Modules and interfaces: use path and content hints
        elif entity.entity_type in ('module', 'interface'):
            if is_verif_path and not is_rtl_path:
                category = 'verification'
            elif is_rtl_path and not is_verif_path:
                category = 'rtl'
            else:
                # Ambiguous - use content hints
                name_lower = entity.name.lower()
                if any(h in name_lower for h in ['_tb', 'testbench', '_test', '_checker']):
                    category = 'verification'
                elif any(h in name_lower for h in ['_if', '_intf', 'interface']):
                    category = 'verification'  # Interfaces are usually for TB
                elif entity.imports and any('uvm' in imp.lower() for imp in entity.imports):
                    category = 'verification'
                else:
                    category = 'rtl'  # Default assumption

        return (category, role)

    def _entity_to_item(self, entity: SVEntity) -> Dict[str, Any]:
        """Convert an SVEntity to a BAM item dictionary."""
        # Classify the entity
        category, role = self._classify_entity(entity)

        # Map entity types to BAM node types
        type_mapping = {
            "module": "RTLModule",
            "interface": "RTLInterface",
            "package": "RTLPackage",
            "class": "VerificationClass",
        }

        item = {
            "id": f"{entity.entity_type}-{entity.name}",
            "name": entity.name,
            "type": type_mapping.get(entity.entity_type, entity.entity_type),
            "file_path": entity.file_path,
            "line_number": entity.line_number,
            "properties": {
                "entity_type": entity.entity_type,
            }
        }

        # Add classification (helpful for agents understanding the codebase)
        if category:
            item["category"] = category
        if role:
            item["role"] = role

        if entity.description:
            item["description"] = entity.description

        if entity.parameters:
            item["properties"]["parameters"] = entity.parameters
            item["properties"]["parameter_count"] = len(entity.parameters)

        if entity.ports:
            item["properties"]["ports"] = entity.ports
            item["properties"]["port_count"] = len(entity.ports)
            item["properties"]["input_count"] = sum(
                1 for p in entity.ports if p["direction"] == "input"
            )
            item["properties"]["output_count"] = sum(
                1 for p in entity.ports if p["direction"] == "output"
            )

        if entity.imports:
            item["properties"]["imports"] = entity.imports

        if entity.includes:
            item["properties"]["includes"] = entity.includes

        if entity.extends:
            item["properties"]["extends"] = entity.extends

        if entity.instantiates:
            item["properties"]["instantiates"] = [
                inst["module"] for inst in entity.instantiates
            ]
            item["properties"]["instance_count"] = len(entity.instantiates)

        if entity.functions:
            item["properties"]["functions"] = entity.functions

        if entity.tasks:
            item["properties"]["tasks"] = entity.tasks

        return item

    def _generate_summary(self, result: ExtractionResult) -> Dict[str, Any]:
        """Generate a summary to help agents quickly understand the codebase.

        This summary provides:
        - Counts by type and category
        - Key entry points (top-level modules, test classes)
        - Directory structure hints
        """
        summary = {
            "total_items": len(result.items),
            "total_relationships": len(result.relationships),
            "by_type": {},
            "by_category": {},
            "by_role": {},
            "top_level_modules": [],
            "test_classes": [],
            "directories": set(),
        }

        # Track which modules are instantiated (have incoming edges)
        instantiated_modules = set()
        for rel in result.relationships:
            if rel.get("type") == "INSTANTIATES":
                instantiated_modules.add(rel.get("target"))

        for item in result.items:
            # Count by type
            item_type = item.get("type", "unknown")
            summary["by_type"][item_type] = summary["by_type"].get(item_type, 0) + 1

            # Count by category
            category = item.get("category", "unknown")
            summary["by_category"][category] = summary["by_category"].get(category, 0) + 1

            # Count by role (for verification classes)
            role = item.get("role")
            if role:
                summary["by_role"][role] = summary["by_role"].get(role, 0) + 1

            # Find top-level modules (not instantiated by others in this source)
            if item_type == "RTLModule" and item["name"] not in instantiated_modules:
                summary["top_level_modules"].append(item["name"])

            # Find test classes
            if role == "test":
                summary["test_classes"].append(item["name"])

            # Track directories
            file_path = item.get("file_path", "")
            if "/" in file_path or "\\" in file_path:
                dir_path = file_path.rsplit("/", 1)[0].rsplit("\\", 1)[0]
                # Get last 2 directory components for brevity
                parts = dir_path.replace("\\", "/").split("/")
                if len(parts) >= 2:
                    summary["directories"].add("/".join(parts[-2:]))

        # Convert set to sorted list
        summary["directories"] = sorted(summary["directories"])

        # Limit lists for readability
        if len(summary["top_level_modules"]) > 10:
            summary["top_level_modules"] = summary["top_level_modules"][:10] + ["..."]
        if len(summary["test_classes"]) > 10:
            summary["test_classes"] = summary["test_classes"][:10] + ["..."]

        return summary

    def to_bam_format(self, result: ExtractionResult) -> Dict[str, Any]:
        """Convert extraction result to BAM ingestion format.

        Args:
            result: ExtractionResult from extract_directory.

        Returns:
            Dictionary ready for BAM pipeline ingestion.
        """
        summary = self._generate_summary(result)

        return {
            "fetchedAt": result.timestamp,
            "source": result.source_id,
            "extractor": self.EXTRACTOR_TYPE,
            "summary": summary,  # Quick overview for agents
            "metadata": {
                "file_count": result.file_count,
                **result.metadata
            },
            "items": result.items,
            "relationships": result.relationships,
            "warnings": result.warnings
        }
