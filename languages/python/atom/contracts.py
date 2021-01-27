from lazycontract import LazyContract, LazyProperty
from lazycontract.contract import (
    LazyContractDeserializationError,
    LazyContractValidationError,
)


class BinaryProperty(LazyProperty):
    _type = bytes

    def deserialize(self, obj):
        if isinstance(obj, self._type):
            return obj
        elif isinstance(obj, str):
            return obj.encode()
        else:
            raise LazyContractDeserializationError("Must provide bytes object")


class RawContract(LazyContract):
    def __init__(self, *args, **kwargs):
        if len(args) + len(kwargs) != 1 or (len(kwargs) == 1 and "data" not in kwargs):
            raise LazyContractValidationError(
                "Raw contracts must store a single data value"
            )

        # If single unkeyed value passed in, automatically map it to the data
        #   field
        if len(args) == 1:
            kwargs["data"] = args[0]
            args = []

        super(RawContract, self).__init__(*args, **kwargs)

        # Validate that data property was created, is marked required, and is
        #   the only property on the contract
        if (
            "data" not in self._properties
            or not self._properties["data"].required
            or len(self._properties) > 1
        ):
            raise LazyContractValidationError(
                "Raw contracts must specify a required data field name. No other fields are allowed."
            )

    def to_dict(self):
        raise TypeError(
            "Cannot convert raw contract to dict, use the to_data() function instead"
        )

    def to_data(self):
        return self.data


class EmptyContract(LazyContract):
    def __init__(self, *args, **kwargs):
        super(EmptyContract, self).__init__(*args, **kwargs)
        is_empty = True
        if len(args) + len(kwargs) > 1:
            is_empty = False
        if len(args) == 1 and args[0] != "" and args[0] != b"":
            is_empty = False
        if len(kwargs) == 1 and (
            "data" not in kwargs or (kwargs["data"] != "" and kwargs["data"] != b"")
        ):
            is_empty = False

        if not is_empty or len(self._properties) > 0:
            raise LazyContractValidationError(
                "Empty contract should contain no data and no field definitions"
            )

    def to_dict(self):
        raise TypeError(
            "Cannot convert empty contract to dict, use the to_data() function instead"
        )

    def to_data(self):
        return ""
