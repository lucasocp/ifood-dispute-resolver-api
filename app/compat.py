"""
Módulo de compatibilidade e abstração de schema.
Permite interoperabilidade transparente entre Pydantic (v2) e Dataclasses nativas do Python.
"""
try:
    from pydantic import BaseModel, Field
    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False
    from dataclasses import dataclass, field, asdict

    def Field(*args, default=..., default_factory=..., description=None, ge=None, le=None, **kwargs):
        if default_factory is not ...:
            return field(default_factory=default_factory)
        if default is not ...:
            return field(default=default)
        return field()

    class BaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

        def dict(self):
            return self.model_dump()

        def model_dump(self):
            res = {}
            for k, v in self.__dict__.items():
                if isinstance(v, BaseModel):
                    res[k] = v.model_dump()
                elif isinstance(v, list):
                    res[k] = [item.model_dump() if isinstance(item, BaseModel) else item for item in v]
                elif hasattr(v, "value"):
                    res[k] = v.value
                else:
                    res[k] = v
            return res

        def __repr__(self):
            attrs = ", ".join(f"{k}={v!r}" for k, v in self.__dict__.items())
            return f"{self.__class__.__name__}({attrs})"
