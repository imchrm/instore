"""Тесты автомата состояний задачи и доменных ошибок."""

from __future__ import annotations

import pytest

from stories_backend.domain.entities import Job, can_transition
from stories_backend.domain.enums import ErrorCode, JobStatus, StoriesFit
from stories_backend.domain.errors import (
    DomainError,
    InvalidStatusTransitionError,
    TooLargeError,
    error_for_code,
)

VALID_TRANSITIONS: list[tuple[JobStatus, JobStatus]] = [
    (JobStatus.QUEUED, JobStatus.DOWNLOADING),
    (JobStatus.QUEUED, JobStatus.FAILED),
    (JobStatus.DOWNLOADING, JobStatus.TRANSCODING),
    (JobStatus.DOWNLOADING, JobStatus.FAILED),
    (JobStatus.TRANSCODING, JobStatus.SEGMENTING),
    (JobStatus.TRANSCODING, JobStatus.FAILED),
    (JobStatus.SEGMENTING, JobStatus.PROBING),
    (JobStatus.SEGMENTING, JobStatus.FAILED),
    (JobStatus.PROBING, JobStatus.READY),
    (JobStatus.PROBING, JobStatus.FAILED),
    (JobStatus.READY, JobStatus.EXPIRED),
]

INVALID_TRANSITIONS: list[tuple[JobStatus, JobStatus]] = [
    (JobStatus.QUEUED, JobStatus.READY),
    (JobStatus.DOWNLOADING, JobStatus.READY),
    (JobStatus.READY, JobStatus.FAILED),
    (JobStatus.READY, JobStatus.DOWNLOADING),
    (JobStatus.FAILED, JobStatus.DOWNLOADING),
    (JobStatus.EXPIRED, JobStatus.READY),
    (JobStatus.QUEUED, JobStatus.QUEUED),
]

TERMINAL_STATES: list[JobStatus] = [JobStatus.FAILED, JobStatus.EXPIRED]


def make_job(status: JobStatus) -> Job:
    return Job(
        job_id="job-1",
        key_id="key-1",
        url="https://example.com/video",
        segment_time=45,
        max_height=1080,
        stories_fit=StoriesFit.NONE,
        use_cookies=False,
        status=status,
    )


@pytest.mark.parametrize(("src", "dst"), VALID_TRANSITIONS)
def test_valid_transition_is_allowed(src: JobStatus, dst: JobStatus) -> None:
    assert can_transition(src, dst) is True

    job = make_job(src)
    job.transition_to(dst)
    assert job.status is dst


@pytest.mark.parametrize(("src", "dst"), INVALID_TRANSITIONS)
def test_invalid_transition_is_rejected(src: JobStatus, dst: JobStatus) -> None:
    assert can_transition(src, dst) is False

    job = make_job(src)
    with pytest.raises(InvalidStatusTransitionError) as exc_info:
        job.transition_to(dst)

    assert exc_info.value.src is src
    assert exc_info.value.dst is dst
    assert exc_info.value.code is ErrorCode.INTERNAL
    # Статус не должен меняться при отклонённом переходе.
    assert job.status is src


@pytest.mark.parametrize("state", TERMINAL_STATES)
def test_terminal_states_have_no_outgoing_transitions(state: JobStatus) -> None:
    assert all(not can_transition(state, dst) for dst in JobStatus)


def test_mark_failed_sets_code_and_message() -> None:
    job = make_job(JobStatus.DOWNLOADING)
    job.mark_failed(ErrorCode.TOO_LARGE, "исходник больше лимита")

    assert job.status is JobStatus.FAILED
    assert job.error_code is ErrorCode.TOO_LARGE
    assert job.error_message == "исходник больше лимита"


def test_domain_error_default_message_from_code() -> None:
    error = TooLargeError()
    assert error.code is ErrorCode.TOO_LARGE
    assert error.message == ErrorCode.TOO_LARGE.value
    assert isinstance(error, DomainError)


def test_domain_error_custom_message() -> None:
    error = TooLargeError("файл 80 МБ при лимите 50")
    assert error.message == "файл 80 МБ при лимите 50"


def test_error_for_code_returns_matching_class() -> None:
    for code in ErrorCode:
        exc_type = error_for_code(code)
        assert issubclass(exc_type, DomainError)
        assert exc_type.code is code
