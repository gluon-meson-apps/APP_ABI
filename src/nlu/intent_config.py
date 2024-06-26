import os

import yaml


class IntentConfig:
    def __init__(
        self,
        name,
        description,
        business,
        action,
        slots,
        disabled,
        examples=None,
        has_children=False,
        full_name_of_parent_intent=None,
        slot_expression=None,
        ignore_previous_slots=False,
        display_name=None,
        hints=None,
        display_examples=None,
    ):
        self.name = name
        self.description = description
        self.action = action
        self.slots = slots
        self.business = business
        self.disabled = disabled
        self.examples = examples or []
        self.has_children = has_children or False
        self.full_name_of_parent_intent: str = full_name_of_parent_intent
        self.slot_expression = slot_expression
        self.ignore_previous_slots = ignore_previous_slots
        self.display_name = display_name
        self.hints = hints
        self.display_examples = display_examples

    def is_ancestor_of(self, other_intent: "IntentConfig"):
        if other_intent.full_name_of_parent_intent and other_intent.full_name_of_parent_intent.startswith(
            self.get_full_intent_name()
        ):
            return True
        return False

    def get_full_intent_name(self) -> str:
        return f"{self.full_name_of_parent_intent}.{self.name}" if self.full_name_of_parent_intent else self.name

    def minial_info(self):
        return {
            "name": self.name,
            "description": self.description,
        }


class IntentListConfig:
    def __init__(self, intents: list[IntentConfig]):
        self.intents = intents
        self._initialize_fixed_intents()

    def _initialize_fixed_intents(self):
        fixed_intents = [
            ("positive", "confirm", False, "positive", [], False),
            ("negative", "denied", False, "negative", [], False),
        ]

        for intent_data in fixed_intents:
            name, description, business, action, slots, disabled = intent_data
            intent = IntentConfig(name, description, business, action, slots, disabled)
            self.intents.append(intent)

    def get_intent_list(self) -> list[IntentConfig]:
        return self.intents

    def get_intent_name_list_by_their_parent_intent(self, parent_intent: str = None):
        # read resources/intent.yaml file and get intent list
        return [
            intent.name
            for intent in self.intents
            if intent.name != "unknown" and intent.full_name_of_parent_intent == parent_intent
        ]

    def get_children_intents(self, current_intent: IntentConfig):
        children_intents = []
        if current_intent.has_children:
            children_intents = [intent for intent in self.intents if current_intent.is_ancestor_of(intent)]
        return children_intents

    def get_intent(self, intent_name):
        return next((intent for intent in self.intents if intent.name == intent_name), None)

    def get_intent_and_attrs(self):
        return [
            {
                "intent": intent.name,
                "examples": intent.examples,
                "description": intent.description,
            }
            for intent in self.intents
        ]

    @classmethod
    def from_scenes(cls, folder_path, parent_intent_full_name: str = None):
        intents = []
        files = [f for f in os.listdir(folder_path) if f.endswith(".yaml")]

        for file_name in files:
            file_path = os.path.join(folder_path, file_name)

            with open(file_path, "r", encoding="utf-8") as file:
                data = yaml.safe_load(file)
            intent_name = data.get("name")

            if data.get("has_children"):
                full_name = f"{parent_intent_full_name}.{intent_name}" if parent_intent_full_name else intent_name
                children_intents = cls.from_scenes(f"{folder_path}/{intent_name}", full_name)
                intents.extend(children_intents.intents)
            intent = IntentConfig(
                name=intent_name,
                description=data.get("description"),
                business=data.get("business"),
                action=data.get("action"),
                slots=data.get("slots"),
                disabled=data.get("disabled", False),
                has_children=data.get("has_children"),
                full_name_of_parent_intent=parent_intent_full_name,
                slot_expression=data.get("slot_expression"),
                ignore_previous_slots=data.get("ignore_previous_slots", False),
                display_name=data.get("display_name"),
                hints=data.get("hints"),
                examples=data.get("examples"),
                display_examples=data.get("display_examples"),
            )
            intents.append(intent)

        return cls(intents)
