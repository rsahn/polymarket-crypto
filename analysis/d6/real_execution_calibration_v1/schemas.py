"""Strict scalar and provenance helpers; no truthiness-based authority."""
import inspect,re
from .core import dec

def text(value):
    if type(value) is not str or not value:raise ValueError('STRING_REQUIRED')
    return value

def integer(value):
    if type(value) is not int or value<0:raise ValueError('INTEGER_REQUIRED')
    return value

def hash256(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}',value) is None:raise ValueError('SHA256_REQUIRED')
    return value

def identifiers(value):
    if type(value) is not list or any(type(v) is not str or not v for v in value) or len(set(value))!=len(value):raise ValueError('UNIQUE_IDENTIFIERS_REQUIRED')
    return value

def authenticate(authority,record):
    result=authority.verify(record)
    if inspect.isawaitable(result):
        if inspect.iscoroutine(result):result.close()
        raise ValueError('SYNC_AUTHORITY_REQUIRED')
    if result is not True:raise ValueError('AUTHORITY_REJECTED')

def frontier(value):
    if type(value) is not dict or set(value)!= {'sequence','digest'}:raise ValueError('FRONTIER_SCHEMA')
    integer(value['sequence']);hash256(value['digest'])
    return value
