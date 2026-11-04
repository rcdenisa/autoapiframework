# *******************************************************************************
# Copyright (c) 2026 ZF Friedrichshafen AG
#
# See the NOTICE file(s) distributed with this work for additional
# information regarding copyright ownership.
#
# This program and the accompanying materials are made available under the
# terms of the Apache License Version 2.0 which is available at
# https://www.apache.org/licenses/LICENSE-2.0
#
# SPDX-License-Identifier: Apache-2.0
# *******************************************************************************
#
# afs_model.py
#
# Pydantic v2 models for the AutoAPI Function Specification (.afs) file format.
# Mirrors the Eclipse-autoapiframework-Metamodel v0.4.1 as defined in
# autoapiframework_metadata_V04.yaml.
#
# PURPOSE:
#   These models are used by validate_afs.py and generate_adapter.py.
#   They provide structured, type-checked access to .afs content loaded
#   from YAML. Any field that does not match the meta model raises a
#   ValidationError with a clear message — no silent failures.
#
# EXPECTATIONS:
#   - Every mandatory field in the meta model is marked as required here.
#   - Optional fields use Optional[...] = None.
#   - Enum types match exactly the values defined in the meta model.
#   - A ValidationError means the .afs file is non-conformant.

from __future__ import annotations

from enum import Enum
from typing import Any, List, Optional, Union

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Enumerations (from metamodel.enums)
# ---------------------------------------------------------------------------

class ASIL(str, Enum):
    """Safety Integrity Level. QM = not safety-relevant."""
    QM = "QM"
    A  = "A"
    B  = "B"
    C  = "C"
    D  = "D"


class Direction(str, Enum):
    """Direction of a Data interface relative to the function."""
    input  = "input"
    output = "output"


class RunType(str, Enum):
    """Activation type of a runnable."""
    init      = "init"
    cyclic    = "cyclic"
    event     = "event"
    terminate = "terminate"


class FunctionResult(str, Enum):
    """Generic execution outcome. Does NOT encode function-specific errors."""
    success      = "success"
    failure      = "failure"
    notAvailable = "notAvailable"


class ErrorSeverity(str, Enum):
    information = "information"
    warning     = "warning"
    degraded    = "degraded"
    shutdown    = "shutdown"


class SupervisionType(str, Enum):
    none     = "none"
    alive    = "alive"
    deadline = "deadline"
    logical  = "logical"
    combined = "combined"


# ---------------------------------------------------------------------------
# Runtime companion (nested inside DataInterface)
# ---------------------------------------------------------------------------

class QualityCodeCompanion(BaseModel):
    """Runtime quality qualifier accompanying a Data interface."""
    name:     str
    datatype: str   # expected: "enum"
    enumRef:  str   # expected: "DataQuality"


class RuntimeCompanion(BaseModel):
    qualityCode: Optional[QualityCodeCompanion] = None


# ---------------------------------------------------------------------------
# Interface types
# ---------------------------------------------------------------------------

class DataInterface(BaseModel):
    """
    Data interface (metamodel interfaceType: Data).
    Mandatory fields mirror the meta model. ASIL is optional because
    it is only required when FuSa == True, but we allow it freely here
    and enforce the FuSa/ASIL consistency in validate_afs.py.

    Fields marked as "Null if not yet defined or not applicable" in the
    meta model accept None here; their presence is checked semantically
    in validate_afs.py when strict mode is needed.

    Note: the field is named 'ASIL' in the .afs YAML. We use Field(alias)
    to avoid a name clash with the ASIL enum class defined above.
    """
    name:               str
    direction:          Direction
    dataType:           str
    description:        str
    unit:               str
    min:                Optional[Union[float, int]]   = None   # null if not yet defined
    max:                Optional[Union[float, int]]   = None   # null if not yet defined
    defaultValue:       Any                           = None
    resolution:         Optional[Union[float, int]]   = None   # null if not yet defined
    precision:          Optional[Union[float, int]]   = None   # null if not yet defined
    FuSa:               bool
    asil:               Optional[ASIL] = Field(default=None, alias="ASIL")
    minUpdatePeriodMs:  int
    accuracy:           Optional[str]                 = None   # null if not yet defined
    protectionRequired: bool
    runtimeCompanion:   Optional[RuntimeCompanion]    = None

    model_config = {"populate_by_name": True}


class ParameterInterface(BaseModel):
    """
    Parameter / calibration interface (metamodel interfaceType: Parameter).
    min/max accept None per meta model ("if defined/applicable").
    """
    name:         str
    dataType:     str
    defaultValue: Any
    description:  str
    unit:         str
    tunable:      bool
    min:          Optional[Union[float, int]] = None
    max:          Optional[Union[float, int]] = None
    dimensions:   Optional[Any] = None   # e.g. [10] or [7, 10]


# ---------------------------------------------------------------------------
# Supervision sub-models
# ---------------------------------------------------------------------------

class AliveSupervision(BaseModel):
    minIndications:   Optional[int]   = None
    maxIndications:   Optional[int]   = None
    referenceCycleMs: Optional[float] = None


class DeadlineSupervision(BaseModel):
    maxExecutionTimeMs: float


class LogicalSupervision(BaseModel):
    predecessorRefs: Optional[List[str]] = None
    successorRefs:   Optional[List[str]] = None


class Supervision(BaseModel):
    required: bool
    type:     Optional[List[str]]              = None  # alive | deadline | logical
    alive:    Optional[AliveSupervision]       = None
    deadline: Optional[DeadlineSupervision]    = None
    logical:  Optional[LogicalSupervision]     = None

    @model_validator(mode="after")
    def check_type_required_when_active(self) -> "Supervision":
        if self.required and not self.type:
            raise ValueError(
                "supervision.type must be specified when supervision.required is True"
            )
        return self


class ExecutionResult(BaseModel):
    """
    References the enum type used for execution result reporting.
    In the .afs, 'type' holds the name of the enum (e.g. "FunctionResult"),
    not an actual value from that enum. It is a type declaration, not a value.
    """
    type: str   # e.g. "FunctionResult" — references the FunctionResult enum type


# ---------------------------------------------------------------------------
# Scheduling entry
# ---------------------------------------------------------------------------

class SchedulingEntry(BaseModel):
    """
    One runnable lifecycle entry (metamodel interfaceType: Scheduling).
    """
    functionName:       str
    runType:            RunType
    description:        str
    implementedASIL:    ASIL
    executionResult:    ExecutionResult
    supervision:        Supervision
    cycleTimeMs:        Optional[float] = None
    previousRunnableRef: Optional[str] = None
    schedulingPolicy:   Optional[str]  = None
    stackSizeBytes:     Optional[int]  = None

    @model_validator(mode="after")
    def check_cycle_time_for_cyclic(self) -> "SchedulingEntry":
        if self.runType == RunType.cyclic and self.cycleTimeMs is None:
            raise ValueError(
                f"cycleTimeMs is mandatory when runType is 'cyclic' "
                f"(runnable: {self.functionName})"
            )
        return self


# ---------------------------------------------------------------------------
# Error interface (candidate status in meta model)
# ---------------------------------------------------------------------------

class ErrorInterface(BaseModel):
    """
    Error interface — candidate status in meta model v0.4.1.
    Not yet formally required; included for forward compatibility.
    """
    name:             str
    dataType:         str
    description:      str
    severity:         Optional[ErrorSeverity] = None
    maturationTimeMs: float
    resetTimeMs:      Optional[float]         = None
    resetCondition:   Optional[str]           = None
    dependencyRefs:   Optional[List[str]]     = None
    fallbackBehavior: Optional[str]           = None
    raisesSafetyReactionRefs: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# Meta model reference
# ---------------------------------------------------------------------------

class MetaModelRef(BaseModel):
    name:    str
    version: str


# ---------------------------------------------------------------------------
# Top-level Function Specification
# ---------------------------------------------------------------------------

class FunctionSpecificationContent(BaseModel):
    """
    Content of the functionSpecification key in an .afs file.
    """
    name:           str
    version:        str
    metaModelRef:   MetaModelRef
    description:    str
    dataInterfaces: List[DataInterface]         = Field(default_factory=list)
    parameters:     List[ParameterInterface]    = Field(default_factory=list)
    scheduling:     List[SchedulingEntry]       = Field(default_factory=list)
    errors:         Optional[List[ErrorInterface]] = None


class FunctionSpecificationFile(BaseModel):
    """
    Root model. An .afs file always has a single 'functionSpecification' key.
    """
    functionSpecification: FunctionSpecificationContent
