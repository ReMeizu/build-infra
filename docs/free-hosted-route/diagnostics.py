"""Fixed public diagnostics: no arbitrary exception, stderr, URL or token text."""
from pathlib import PurePosixPath
import re

SOURCE_MESSAGES={
    'SOURCE_BYTES_MISMATCH':'public input byte mismatch',
    'SOURCE_SIZE_MISMATCH':'public input size mismatch',
    'SOURCE_MODE_MISMATCH':'public input mode mismatch',
    'SOURCE_LINK_MISMATCH':'public input link differs',
    'SOURCE_LINK_ESCAPE':'public input link escapes admitted source root',
    'SOURCE_OWNER_MISSING':'source member has no exact pinned project owner',
    'SOURCE_GIT_LINK_MISMATCH':'Git source link differs from admitted original member',
    'SOURCE_GIT_EXECUTABLE_MISMATCH':'Git executable bit differs from admitted source member',
}
FIXED_VALUES={
    'anonymous canonical HTTPS input required':'PUBLIC_HTTPS_CANONICAL_REFUSAL',
    'public source host outside reviewed allowlist':'PUBLIC_HOST_REFUSAL',
    'new verified source download required':'PUBLIC_DOWNLOAD_EXISTS',
    'download exact size/hash missing':'PUBLIC_DOWNLOAD_PIN_MISSING',
    'public input exceeds exact admitted length':'PUBLIC_DOWNLOAD_EXCEEDS_SIZE',
    'public input full size/hash differs':'PUBLIC_DOWNLOAD_SHA_SIZE_MISMATCH',
    'unsupported original tool extraction prefix':'PUBLIC_TOOL_PREFIX_REFUSAL',
    'tool output collision':'PUBLIC_TOOL_OUTPUT_COLLISION',
    'tool absolute symlink':'PUBLIC_TOOL_ABSOLUTE_LINK',
    'tool archive special member refused':'PUBLIC_TOOL_SPECIAL_MEMBER',
    'incomplete exact tool member mapping':'PUBLIC_TOOL_MEMBER_MAPPING_MISMATCH',
    'reviewed source-only public acquisition lock required':'PUBLIC_LOCK_SCOPE_REFUSAL',
    'genuine 88/72 intermediate required; full375 not admitted':'PUBLIC_COHORT_REFUSAL',
    'public source project coverage differs':'PUBLIC_PROJECT_COVERAGE_MISMATCH',
    'public source original pin changed':'PUBLIC_PROJECT_PIN_MISMATCH',
    'official tool root coverage differs':'PUBLIC_TOOL_COVERAGE_MISMATCH',
    'offline wheel coverage differs':'PUBLIC_WHEEL_COVERAGE_MISMATCH',
    'fresh public source acquisition root required':'PUBLIC_SOURCE_ROOT_EXISTS',
    'public GN inventory hash differs':'PUBLIC_GN_INVENTORY_MISMATCH',
    'actual disk cannot retain verified source/tools/downloads/Docker headroom':'PUBLIC_DISK_CAPACITY_REFUSAL',
    'opaque/private carrier member in thin source export':'PUBLIC_CARRIER_SCOPE_REFUSAL',
    'anonymous fetched original Git identity differs':'PUBLIC_FETCHED_GIT_IDENTITY_MISMATCH',
    'unsafe public source path':'PUBLIC_PATH_REFUSAL',
}

def public_member(value):
    if not isinstance(value,str) or not 0<len(value)<=512 or any(ord(c)<32 or ord(c)==127 for c in value):return None
    path=PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or str(path)!=value or any(x in value for x in (':','\\','?','=','%')):return None
    if re.search(r'gh[pousr]_|github_pat_|PRIVATE KEY',value,re.I):return None
    return value

class PublicInputError(ValueError):
    def __init__(self,code,member=None):
        if code not in SOURCE_MESSAGES:raise ValueError('unknown fixed public source diagnostic')
        super().__init__(SOURCE_MESSAGES[code])
        self.public_code=code
        self.public_member=public_member(member)

def diagnostic(error):
    known_types={'ValueError','PublicInputError','OSError','FileNotFoundError','PermissionError','FileExistsError',
                 'HTTPError','URLError','CalledProcessError','TimeoutExpired','KeyboardInterrupt','JSONDecodeError',
                 'KeyError','TypeError','RuntimeError','BrokenPipeError'}
    name=type(error).__name__
    result={'error_type':name if name in known_types else 'Exception'}
    if isinstance(error,PublicInputError):
        result['error_code']=error.public_code
        if error.public_member is not None:result['declared_public_member']=error.public_member
    elif type(error) is ValueError:
        result['error_code']=FIXED_VALUES.get(str(error),'UNCLASSIFIED_VALUE_ERROR')
    else:
        result['error_code']='UNCLASSIFIED_EXCEPTION'
    # Only bounded source-owned function/line identity; never traceback text.
    tb=error.__traceback__
    allowed={'acquire.py','free_native_run.py','make_j2_successor.py','resource.py','finish_attempt.py','diagnostics.py'}
    while tb:
        name=PurePosixPath(tb.tb_frame.f_code.co_filename).name
        function=tb.tb_frame.f_code.co_name
        if name in allowed and re.fullmatch('[A-Za-z_][A-Za-z_0-9]{0,63}',function):
            result['source_check']={'module':name,'function':function,'line':tb.tb_lineno}
        tb=tb.tb_next
    return result
