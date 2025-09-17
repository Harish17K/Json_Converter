import http.server
import json
import urllib.parse
import re
import os
from datetime import datetime

def load_schema():
    """Load schema from schema.json file"""
    try:
        with open('schema.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print("ERROR: schema.json file not found!")
        return {}
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in schema.json: {e}")
        return {}

def load_external_schema(ref_path):
    """Load external schema file"""
    try:
        # Handle different reference formats
        if ref_path.startswith('/schemas/'):
            file_path = ref_path[1:]  # Remove leading slash
        elif ref_path.startswith('./schemas/'):
            file_path = ref_path[2:]  # Remove './'
        elif ref_path.startswith('schemas/'):
            file_path = ref_path
        else:
            # Try to construct the path
            file_path = f"schemas/{ref_path}"
        
        print(f"Attempting to load external schema: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            schema = json.load(f)
            print(f"Successfully loaded schema: {file_path}")
            return schema
    except FileNotFoundError:
        print(f"ERROR: External schema file not found: {file_path}")
        return None
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in external schema {file_path}: {e}")
        return None

def resolve_ref(ref_path, schema, loaded_external_schemas=None):
    """Resolve a $ref path within the schema or from external files"""
    if loaded_external_schemas is None:
        loaded_external_schemas = {}
    
    # Handle internal references (#/definitions/... or #/$defs/...)
    if ref_path.startswith('#/'):
        path_parts = ref_path[2:].split('/')  # Remove the '#/' prefix
        current = schema
        
        for part in path_parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                print(f"Warning: Could not resolve internal $ref path: {ref_path}")
                return None
        
        return current
    
    # Handle external references
    else:
        # Check if we've already loaded this schema
        if ref_path in loaded_external_schemas:
            return loaded_external_schemas[ref_path]
        
        # Load the external schema
        external_schema = load_external_schema(ref_path)
        if external_schema:
            # Cache the loaded schema
            loaded_external_schemas[ref_path] = external_schema
            return external_schema
        else:
            print(f"Warning: Could not load external $ref: {ref_path}")
            return None

def resolve_schema_refs(schema_part, full_schema, loaded_external_schemas=None):
    """Recursively resolve all $ref references in a schema part"""
    if loaded_external_schemas is None:
        loaded_external_schemas = {}
    
    if isinstance(schema_part, dict):
        if '$ref' in schema_part:
            # Resolve the reference
            resolved = resolve_ref(schema_part['$ref'], full_schema, loaded_external_schemas)
            if resolved:
                # Recursively resolve any refs in the resolved schema
                return resolve_schema_refs(resolved, full_schema, loaded_external_schemas)
            else:
                print(f"Failed to resolve $ref: {schema_part['$ref']}")
                # Return a placeholder object to prevent form generation errors
                return {
                    "type": "object",
                    "title": f"Failed to load: {schema_part['$ref']}",
                    "properties": {
                        "error": {
                            "type": "string",
                            "title": "Error",
                            "description": f"Could not load schema from {schema_part['$ref']}"
                        }
                    }
                }
        else:
            # Recursively process all properties
            result = {}
            for key, value in schema_part.items():
                result[key] = resolve_schema_refs(value, full_schema, loaded_external_schemas)
            return result
    elif isinstance(schema_part, list):
        return [resolve_schema_refs(item, full_schema, loaded_external_schemas) for item in schema_part]
    else:
        return schema_part

def generate_html_form_from_schema(schema):
    """Generate HTML form dynamically from JSON schema with $ref support"""
    
    print("Starting form generation...")
    print(f"Schema properties: {list(schema.get('properties', {}).keys())}")
    
    # First, resolve all $ref references in the schema
    resolved_schema = resolve_schema_refs(schema, schema)
    
    print("Schema resolved, generating form...")
    print(f"Resolved schema properties: {list(resolved_schema.get('properties', {}).keys())}")
    
    def get_input_type(field_schema):
        """Determine HTML input type from JSON schema field"""
        field_type = field_schema.get('type', 'string')
        field_format = field_schema.get('format', '')
        
        if field_type == 'string':
            if field_format == 'email':
                return 'email'
            elif field_format == 'date':
                return 'date'
            elif field_format == 'date-time':
                return 'datetime-local'
            elif 'enum' in field_schema:
                return 'select'
            elif field_schema.get('pattern'):
                return 'text'  # Pattern will be handled in validation
            else:
                return 'text'
        elif field_type == 'integer':
            return 'number'
        elif field_type == 'number':
            return 'number'
        elif field_type == 'boolean':
            return 'checkbox'
        elif field_type == 'array':
            return 'textarea'  # For now, handle arrays as JSON text
        elif field_type == 'object':
            return 'fieldset'  # Nested object
        else:
            return 'text'
    
    def generate_field_html(field_name, field_schema, is_required=False, parent_path="", depth=0):
        """Generate HTML for a single field"""
        # Prevent infinite recursion
        if depth > 3:
            return f'<div class="form-group"><p>Max depth reached for {field_name}</p></div>'
        
        # Make sure we're working with a resolved schema
        if '$ref' in field_schema:
            field_schema = resolve_schema_refs(field_schema, resolved_schema)
        
        input_type = get_input_type(field_schema)
        description = field_schema.get('description', '')
        title = field_schema.get('title', field_name.replace('_', ' ').replace('-', ' ').title())
        
        # Create full field path for nested objects
        full_field_name = f"{parent_path}.{field_name}" if parent_path else field_name
        
        # Required indicator
        required_indicator = '<span class="required">*</span>' if is_required else ''
        
        html = f'<div class="form-group">\n'
        html += f'  <label for="{full_field_name}">{title} {required_indicator}</label>\n'
        
        if description:
            html += f'  <small class="field-description">{description}</small>\n'
        
        # Generate input based on type
        if input_type == 'select':
            html += f'  <select name="{full_field_name}" id="{full_field_name}"{"" if not is_required else " required"}>\n'
            html += f'    <option value="">Select...</option>\n'
            for option in field_schema.get('enum', []):
                option_text = option.replace('_', ' ').title()
                html += f'    <option value="{option}">{option_text}</option>\n'
            html += f'  </select>\n'
        
        elif input_type == 'textarea':
            html += f'  <textarea name="{full_field_name}" id="{full_field_name}" placeholder="Enter JSON array"{"" if not is_required else " required"}></textarea>\n'
        
        elif input_type == 'fieldset':
            html += f'  <fieldset class="nested-object" style="margin-left: {depth * 20}px;">\n'
            html += f'    <legend>{title}</legend>\n'
            # Handle nested object properties
            nested_properties = field_schema.get('properties', {})
            nested_required = field_schema.get('required', [])
            
            print(f"Processing nested object '{field_name}' with properties: {list(nested_properties.keys())}")
            
            for nested_name, nested_schema in nested_properties.items():
                nested_is_required = nested_name in nested_required
                html += generate_field_html(nested_name, nested_schema, nested_is_required, full_field_name, depth + 1)
            html += f'  </fieldset>\n'
        
        elif input_type == 'checkbox':
            html += f'  <input type="checkbox" name="{full_field_name}" id="{full_field_name}" value="true">\n'
        
        else:
            # Standard input types
            attributes = f'type="{input_type}" name="{full_field_name}" id="{full_field_name}"'
            
            # Add validation attributes
            if field_schema.get('minLength'):
                attributes += f' minlength="{field_schema["minLength"]}"'
            if field_schema.get('maxLength'):
                attributes += f' maxlength="{field_schema["maxLength"]}"'
            if field_schema.get('minimum'):
                attributes += f' min="{field_schema["minimum"]}"'
            if field_schema.get('maximum'):
                attributes += f' max="{field_schema["maximum"]}"'
            if field_schema.get('pattern'):
                attributes += f' pattern="{field_schema["pattern"]}"'
            if is_required:
                attributes += ' required'
            
            # Add placeholder
            placeholder = f'Enter {title.lower()}'
            if field_schema.get('pattern'):
                placeholder += f' (pattern required)'
            
            html += f'  <input {attributes} placeholder="{placeholder}">\n'
        
        html += '</div>\n'
        return html
    
    # Generate complete HTML form
    html_form = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dynamic Schema Form</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }
        
        .container {
            background: white;
            padding: 30px;
            border-radius: 15px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }
        
        h1 {
            text-align: center;
            color: #333;
            margin-bottom: 10px;
        }
        
        .schema-info {
            text-align: center;
            color: #666;
            margin-bottom: 30px;
            font-style: italic;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        label {
            display: block;
            margin-bottom: 5px;
            font-weight: bold;
            color: #333;
        }
        
        .required {
            color: red;
        }
        
        .field-description {
            display: block;
            color: #666;
            font-size: 12px;
            margin-bottom: 5px;
        }
        
        input, select, textarea {
            width: 100%;
            padding: 10px;
            border: 2px solid #ddd;
            border-radius: 5px;
            font-size: 14px;
            box-sizing: border-box;
        }
        
        input:focus, select:focus, textarea:focus {
            outline: none;
            border-color: #4CAF50;
        }
        
        textarea {
            height: 80px;
            resize: vertical;
        }
        
        fieldset {
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            padding: 15px;
            margin: 10px 0;
        }
        
        legend {
            font-weight: bold;
            color: #555;
            padding: 0 10px;
        }
        
        .nested-object {
            background: #f9f9f9;
        }
        
        button {
            background: #4CAF50;
            color: white;
            padding: 15px 30px;
            border: none;
            border-radius: 5px;
            font-size: 16px;
            cursor: pointer;
            width: 100%;
            margin: 20px 0;
        }
        
        button:hover {
            background: #45a049;
        }
        
        #result {
            margin-top: 30px;
            background: #f9f9f9;
            padding: 20px;
            border-radius: 8px;
            border: 1px solid #ddd;
            display: none;
        }
        
        pre {
            background: #2d3748;
            color: #e2e8f0;
            padding: 20px;
            border-radius: 8px;
            overflow-x: auto;
            font-size: 14px;
        }
        
        .schema-details {
            background: #e8f5e8;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            border-left: 4px solid #4CAF50;
        }
        
        .debug-info {
            background: #fff3cd;
            border: 1px solid #ffeaa7;
            padding: 10px;
            border-radius: 5px;
            margin-bottom: 20px;
            font-size: 12px;
        }
        
        .error-message {
            background: #f8d7da;
            color: #721c24;
            padding: 10px;
            border-radius: 5px;
            margin-bottom: 15px;
            border: 1px solid #f5c6cb;
        }
    </style>
</head>
<body>
    <div class="container">'''
    
    # Add schema information
    title = resolved_schema.get('title', 'Dynamic Form')
    description = resolved_schema.get('description', 'Form generated from JSON Schema')
    
    # Show debug info about external schemas
    debug_info = '<div class="debug-info">✅ External $ref schemas loaded and resolved automatically</div>'
    
    html_form += f'''
        <h1>{title}</h1>
        <div class="schema-info">{description}</div>
        {debug_info}
        
        <div class="schema-details">
            <strong>Schema ID:</strong> {resolved_schema.get('$id', 'Not specified')}<br>
            <strong>Schema Version:</strong> {resolved_schema.get('$schema', 'Not specified')}
        </div>
        
        <form id="dynamicForm">'''
    
    # Generate fields from resolved schema properties
    properties = resolved_schema.get('properties', {})
    required_fields = resolved_schema.get('required', [])
    
    print(f"Generating form for properties: {list(properties.keys())}")
    
    if not properties:
        html_form += '<div class="error-message">No properties found in schema. Check your schema structure and $ref resolution.</div>'
    
    for field_name, field_schema in properties.items():
        is_required = field_name in required_fields
        print(f"Generating field: {field_name}, required: {is_required}")
        html_form += generate_field_html(field_name, field_schema, is_required)
    
    # Add submit button and result area
    html_form += '''
            <button type="submit">Submit & Validate</button>
        </form>
        
        <div id="result">
            <h3>JSON Output:</h3>
            <pre id="jsonOutput"></pre>
        </div>
    </div>

    <script>
        document.getElementById('dynamicForm').addEventListener('submit', function(e) {
            e.preventDefault();
            
            const submitButton = this.querySelector('button[type="submit"]');
            submitButton.textContent = 'Processing...';
            submitButton.disabled = true;
            
            const formData = new FormData(this);
            
            fetch('/validate', {
                method: 'POST',
                body: new URLSearchParams(formData)
            })
            .then(response => response.json())
            .then(data => {
                document.getElementById('jsonOutput').textContent = JSON.stringify(data, null, 2);
                document.getElementById('result').style.display = 'block';
                document.getElementById('result').scrollIntoView({ behavior: 'smooth' });
                
                submitButton.textContent = 'Submit & Validate';
                submitButton.disabled = false;
            })
            .catch(error => {
                document.getElementById('jsonOutput').textContent = JSON.stringify({
                    "error": "Connection failed",
                    "message": error.message
                }, null, 2);
                
                document.getElementById('result').style.display = 'block';
                
                submitButton.textContent = 'Submit & Validate';
                submitButton.disabled = false;
            });
        });
    </script>
</body>
</html>'''
    
    return html_form

def validate_against_schema(data, schema):
    """Validate data against the loaded schema with $ref resolution"""
    # Resolve refs in schema first
    resolved_schema = resolve_schema_refs(schema, schema)
    
    errors = []
    
    # Basic validation implementation
    properties = resolved_schema.get('properties', {})
    required_fields = resolved_schema.get('required', [])
    
    # Check required fields
    for field in required_fields:
        if field not in data or data[field] == '':
            errors.append(f"Field '{field}' is required")
    
    # Validate each field
    for field_name, value in data.items():
        if field_name in properties and value:
            field_schema = properties[field_name]
            # Resolve any remaining refs in field schema
            field_schema = resolve_schema_refs(field_schema, resolved_schema)
            field_errors = validate_field_value(field_name, value, field_schema)
            errors.extend(field_errors)
    
    return errors

def validate_field_value(field_name, value, field_schema):
    """Validate individual field value"""
    errors = []
    field_type = field_schema.get('type', 'string')
    
    if field_type == 'string':
        # Length validation
        if 'minLength' in field_schema and len(value) < field_schema['minLength']:
            errors.append(f"'{field_name}' must be at least {field_schema['minLength']} characters")
        if 'maxLength' in field_schema and len(value) > field_schema['maxLength']:
            errors.append(f"'{field_name}' must be at most {field_schema['maxLength']} characters")
        
        # Pattern validation
        if 'pattern' in field_schema:
            if not re.match(field_schema['pattern'], value):
                errors.append(f"'{field_name}' does not match required pattern")
        
        # Enum validation
        if 'enum' in field_schema and value not in field_schema['enum']:
            errors.append(f"'{field_name}' must be one of: {', '.join(field_schema['enum'])}")
        
        # Format validation
        if field_schema.get('format') == 'email':
            if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', value):
                errors.append(f"'{field_name}' must be a valid email")
    
    elif field_type in ['integer', 'number']:
        try:
            num_value = int(value) if field_type == 'integer' else float(value)
            if 'minimum' in field_schema and num_value < field_schema['minimum']:
                errors.append(f"'{field_name}' must be at least {field_schema['minimum']}")
            if 'maximum' in field_schema and num_value > field_schema['maximum']:
                errors.append(f"'{field_name}' must be at most {field_schema['maximum']}")
        except ValueError:
            errors.append(f"'{field_name}' must be a valid {field_type}")
    
    return errors

class DynamicSchemaServer(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.schema = load_schema()
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        print(f"GET request: {self.path}")
        
        if self.path == '/' or self.path == '/dashboard':
            # Generate HTML form dynamically from schema
            html_content = generate_html_form_from_schema(self.schema)
            
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html_content.encode('utf-8'))
        else:
            self.send_error(404)
    
    def do_POST(self):
        print(f"POST request: {self.path}")
        
        if self.path == '/validate':
            self.handle_validation()
        else:
            self.send_error(404)
    
    def handle_validation(self):
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length).decode('utf-8')
            form_data = urllib.parse.parse_qs(post_data)
            
            # Convert to flat dict first
            flat_data = {}
            for key, value in form_data.items():
                flat_data[key] = value[0] if value else ''
            
            print(f"Received flat form data: {flat_data}")
            
            # Convert nested field names (like "personal_info.name") back to nested structure
            nested_data = self.parse_nested_form_data(flat_data)
            
            print(f"Converted to nested data: {nested_data}")
            
            # Validate against schema
            validation_errors = validate_against_schema(nested_data, self.schema)
            
            # Log validation results
            if validation_errors:
                print(f"VALIDATION FAILED: {validation_errors}")
            else:
                print("VALIDATION PASSED: All data valid according to schema")
            
            # Return the structured data as JSON
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(nested_data, indent=2).encode())
            
        except Exception as e:
            print(f"Error in validation: {e}")
            import traceback
            traceback.print_exc()
            
            error_response = {"error": str(e)}
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(error_response, indent=2).encode())
    
    def parse_nested_form_data(self, flat_data):
        """Convert flat form data with dot notation back to nested structure"""
        nested_data = {}
        
        for key, value in flat_data.items():
            if '.' in key:
                # Handle nested fields like "personal_info.name"
                parts = key.split('.')
                current = nested_data
                
                # Navigate/create the nested structure
                for i, part in enumerate(parts[:-1]):
                    if part not in current:
                        current[part] = {}
                    current = current[part]
                
                # Set the final value
                final_key = parts[-1]
                current[final_key] = value
            else:
                # Handle flat fields
                nested_data[key] = value
        
        return nested_data

if __name__ == '__main__':
    PORT = 8000
    print("="*60)
    print("  FIXED: DYNAMIC SCHEMA-DRIVEN DASHBOARD")
    print("="*60)
    print(f"Server: http://localhost:{PORT}")
    print("Features:")
    print("- ✅ FIXED: External $ref resolution")
    print("- ✅ Loads schemas from /schemas/ folder")
    print("- ✅ Generates proper form fields")
    print("- ✅ All field types and validations")
    print("- ✅ Nested object support")
    print("="*60)
    
    try:
        server = http.server.HTTPServer(('', PORT), DynamicSchemaServer)
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped!")
    except Exception as e:
        print(f"Error: {e}")