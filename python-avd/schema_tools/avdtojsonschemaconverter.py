# Copyright (c) 2023-2024 Arista Networks, Inc.
# Use of this source code is governed by the Apache License 2.0
# that can be found in the LICENSE file.
from __future__ import annotations

from .key_to_display_name import key_to_display_name


def get_deprecation(schema: dict) -> tuple[str, str]:
    """
    Build deprecation details for documentation if deprecation is set on the schema element.

    This function is also imported into avdtojsonschemaconverter

    Returns
    -------
    deprecation_label : str | None
        If deprecated or removed this is "deprecated" or "removed" . Should be added as label
        on the key by the calling function.
    deprecation : str | None
        Deprecation or removal message which should be added to the key comment field by the calling function.
    """
    if (deprecation := schema.get("deprecation")) is None:
        return None, None

    if removed := deprecation.get("removed"):
        removed_verb = "was"
        state_verb = "was"
        state = "removed"
    else:
        removed_verb = "will be"
        state_verb = "is"
        state = "deprecated"

    output = [f"This key {state_verb} {state}."]

    if (remove_in_version := deprecation.get("remove_in_version")) is not None:
        output.append(f"Support {removed_verb} removed in AVD version {remove_in_version}.")
    elif (remove_after_date := deprecation.get("remove_after_date")) is not None:
        output.append(f"Support {removed_verb} removed in the first major AVD version released after {remove_after_date}.")
    elif removed:
        output.append(f"Support {removed_verb} removed in AVD.")

    if (new_key := deprecation.get("new_key")) is not None:
        output.append(f"Use <samp>{new_key}</samp> instead.")

    if (url := deprecation.get("url")) is not None:
        output.append(f"See [here]({url}) for details.")

    return state, " ".join(output)


class AvdToJsonSchemaConverter:
    """
    This class will convert the proprietary AVD Schema to JSON Schema

    A few keywords are converted as part of another keyword, simply because
    of the way JSON Schema is organized compared to AVD Schema.
    - "required"
    - "primary_key"
    - "allow_other_keys"

    Some features of AVD Schema are not supported by JSON Schema:
    - Enforcing uniqueness of "primary_key" in list of dicts
    - "dynamic_keys" based on values of data
    - "dynamic_valid_values" based on values of data
    - Most options under str "format"
    """

    def __init__(self):
        self.converters = {
            "display_name": self.convert_display_name,
            "description": self.convert_description,
            "type": self.convert_type,
            "max": self.convert_max,
            "min": self.convert_min,
            "valid_values": self.convert_valid_values,
            "format": self.convert_format,
            "max_length": self.convert_max_length,
            "min_length": self.convert_min_length,
            "pattern": self.convert_pattern,
            "default": self.convert_default,
            "items": self.convert_items,
            "keys": self.convert_keys,
            # "dynamic_keys": self.convert_dynamic_keys,
        }

    def convert_schema(self, schema: dict) -> dict:
        output = {}
        for word in schema:
            if word not in self.converters:
                # Ignore unsupported keys
                continue

            output.update(self.converters[word](schema[word], schema))

        return output

    def convert_type(self, type: str, _) -> dict:
        TYPE_MAP = {
            "str": "string",
            "int": "integer",
            "bool": "boolean",
            "list": "array",
            "dict": "object",
        }
        return {"type": TYPE_MAP[type]}

    def convert_keys(self, keys: dict, parent_schema: dict) -> dict:
        return self.__convert_keys(keys, parent_schema, "properties")

    def __convert_keys(self, keys: dict, parent_schema: dict, output_key: str, ignore_required: str = False) -> dict:
        """
        Reusable function to convert keys, pattern_keys, $defs
        output_key is set to either "properties", "patternProperties" or "$defs"
        """
        output = {output_key: {}}
        required = []
        for key, subschema in keys.items():
            if "deprecation" in subschema and get_deprecation(subschema)[0] == "removed":
                # Skip key if marked as removed in the AVD schema
                continue

            output[output_key][key] = self.convert_schema(subschema)

            # Add an auto-generated title in case one is not set
            if "title" not in output[output_key][key]:
                output[output_key][key]["title"] = key_to_display_name(str(key))

            if not ignore_required and subschema.get("required") is True:
                required.append(key)

        if required:
            output["required"] = required

        # output["unevaluatedProperties"] = parent_schema.get("allow_other_keys", False)
        output["additionalProperties"] = parent_schema.get("allow_other_keys", False)

        # Always permit keys starting with underscore
        if not parent_schema.get("allow_other_keys", False):
            output.setdefault("patternProperties", {})["^_.+$"] = {}

        return output

    def convert_max(self, max: int, _) -> dict:
        return {"maximum": max}

    def convert_min(self, min: int, _) -> dict:
        return {"minimum": min}

    def convert_valid_values(self, valid_values: list, _) -> dict:
        return {"enum": valid_values}

    def convert_format(self, format: str, _) -> dict:
        FORMAT_MAP = {
            "ipv4": "ipv4",
            "ipv4_cidr": None,
            "ipv6": "ipv6",
            "ipv6_cidr": None,
            "ip": None,
            "cidr": None,
            "mac": None,
        }
        if (newformat := FORMAT_MAP[format]) is None:
            return {}

        return {"format": newformat}

    def convert_max_length(self, max: int, parent_schema: dict) -> dict:
        vartype = parent_schema["type"]
        if vartype == "str":
            return {"maxLength": max}
        if vartype == "list":
            return {"maxItems": max}
        return {}

    def convert_min_length(self, min: int, parent_schema: dict) -> dict:
        vartype = parent_schema["type"]
        if vartype == "str":
            return {"minLength": min}
        if vartype == "list":
            return {"minItems": min}
        return {}

    def convert_pattern(self, pattern: str, _) -> dict:
        return {"pattern": pattern}

    def convert_default(self, default, _) -> dict:
        return {"default": default}

    def convert_items(self, items: dict, parent_schema: dict) -> dict:
        output = {
            "items": self.convert_schema(items),
        }
        if (primary_key := parent_schema.get("primary_key")) and items.get("type") == "dict":
            output["items"].setdefault("required", [])
            if primary_key not in output["items"]["required"]:
                output["items"]["required"].append(primary_key)
        return output

    def convert_display_name(self, display_name: str, _) -> dict:
        return {"title": display_name}

    def convert_description(self, description: str, parent_schema: dict) -> dict:
        if "deprecation" in parent_schema:
            _, deprecation_text = get_deprecation(parent_schema)
            if deprecation_text is not None:
                return {
                    "description": f"{description}\n{deprecation_text}",
                    "deprecated": True,
                }

        return {"description": description}
