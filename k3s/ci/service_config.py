"""Validated, non-secret service registry shared by deployer and scaffolder."""
import json
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent
DEFAULT_DIRECTORY = HERE / 'services' if (HERE / 'services').is_dir() else HERE.parent / 'services'
NAME = r'[a-z][a-z0-9-]{0,39}'
IMAGE = r'docker\.io/[a-z0-9][a-z0-9_-]*/[a-z0-9][a-z0-9_.-]*'
REQUIRED = {'schema_version', 'name', 'repository', 'production_branch', 'image_repository',
            'hostname', 'container_port', 'node_port', 'health_path', 'resources',
            'database', 'legacy_container', 'preflight'}


def match(pattern, value, message):
    if not isinstance(value, str) or re.fullmatch(pattern, value) is None:
        raise ValueError(message)


def validate(config):
    if not isinstance(config, dict) or set(config) != REQUIRED or config['schema_version'] != 1:
        raise ValueError('Service must contain exactly the documented version 1 fields')
    match(NAME, config['name'], 'Invalid service name')
    match(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', config['repository'], 'Invalid GitHub repository')
    match(r'[A-Za-z0-9][A-Za-z0-9_./-]*', config['production_branch'], 'Invalid branch')
    if '..' in config['production_branch'] or config['production_branch'].endswith('/'):
        raise ValueError('Invalid branch')
    match(IMAGE, config['image_repository'], 'Expected untagged docker.io repository')
    match(r'(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}', config['hostname'], 'Invalid hostname')
    for key, low, high in [('container_port', 1, 65535), ('node_port', 30000, 32767)]:
        if type(config[key]) is not int or not low <= config[key] <= high:
            raise ValueError('Invalid ' + key)
    match(r'/[A-Za-z0-9/_-]*', config['health_path'], 'Invalid health path')
    resources = config['resources']
    if not isinstance(resources, dict) or set(resources) != {'cpu_request', 'memory_request', 'memory_limit'}:
        raise ValueError('Explicit resource requests and memory limit required')
    match(r'[1-9][0-9]*m', resources['cpu_request'], 'CPU request must be positive millicores')
    for key in ['memory_request', 'memory_limit']:
        match(r'[1-9][0-9]*Mi', resources[key], 'Memory must be positive Mi')
    if int(resources['memory_request'][:-2]) > int(resources['memory_limit'][:-2]):
        raise ValueError('Memory request exceeds limit')
    if config['legacy_container'] is not None:
        match(r'[A-Za-z0-9][A-Za-z0-9_.-]*', config['legacy_container'], 'Invalid legacy container')
    db = config['database']
    if db is not None:
        if not isinstance(db, dict) or set(db) != {'container', 'name', 'host_ip'}:
            raise ValueError('Database must be null or a host PostgreSQL configuration')
        match(r'[A-Za-z0-9][A-Za-z0-9_.-]*', db['container'], 'Invalid DB container')
        match(r'[a-z][a-z0-9_]{0,62}', db['name'], 'Invalid database name')
        import ipaddress
        if not isinstance(db['host_ip'], str) or ipaddress.ip_address(db['host_ip']).version != 4:
            raise ValueError('Expected host IPv4 address')
    probe = config['preflight']
    if probe is not None:
        if not isinstance(probe, dict) or set(probe) != {'command', 'script', 'memory_limit'}:
            raise ValueError('Invalid preflight configuration')
        if not isinstance(probe['command'], list) or not probe['command'] or not all(isinstance(x, str) and x and '\x00' not in x for x in probe['command']):
            raise ValueError('Preflight command must be a nonempty argv array')
        if probe['script'] is not None:
            match(r'[A-Za-z0-9][A-Za-z0-9_.-]*', probe['script'], 'Preflight script must be a plain filename')
        match(r'[1-9][0-9]*Mi', probe['memory_limit'], 'Invalid preflight memory limit')
        if int(probe['memory_limit'][:-2]) < 32:
            raise ValueError('Preflight limit must cover its 32Mi request')
    return config


def load_service(name, directory=DEFAULT_DIRECTORY):
    match(NAME, name, 'Invalid service name')
    path = pathlib.Path(directory) / (name + '.json')
    try:
        config = validate(json.loads(path.read_text()))
    except FileNotFoundError:
        raise ValueError('Unregistered service: ' + name) from None
    if config['name'] != name:
        raise ValueError('Service filename/name mismatch')
    return config


def load_registry(directory=DEFAULT_DIRECTORY):
    result, ports, hosts = {}, set(), set()
    for path in sorted(pathlib.Path(directory).glob('*.json')):
        config = load_service(path.stem, directory)
        if config['node_port'] in ports or config['hostname'] in hosts:
            raise ValueError('Duplicate NodePort or hostname: ' + config['name'])
        ports.add(config['node_port']); hosts.add(config['hostname'])
        result[config['name']] = config
    return result
