import argparse
import glob
import os
import schema_reader
import yaml
from generators import intermediate_files
from generators import csv_generator
from generators import es_template
from generators import beats
from generators import asciidoc_fields
from generators import ecs_helpers


def main():
    args = argument_parser()

    ecs_version = read_version()
    print('Running generator. ECS version ' + ecs_version)

    # Load the default schemas
    print('Loading default schemas')
    (nested, flat) = schema_reader.load_schemas()

    # Maybe load user specified directory of schemas
    if args.include:
        include_glob = os.path.join(args.include, '*.yml')

        print('Loading user defined schemas: {0}'.format(include_glob))

        (custom_nested, custom_flat) = schema_reader.load_schemas(sorted(glob.glob(include_glob)))

        if args.validate:
            for field in custom_flat:
                if field in flat and custom_flat[field]['type'] != flat[field]['type']:
                    print('Validation failed: field {} has type {} in custom schema but type {} in ECS'.format(field, custom_flat[field]['type'], flat[field]['type']))
                    exit()
            nested = custom_nested
            flat = custom_flat
        else:
            # Merge without allowing user schemas to overwrite default schemas
            nested = ecs_helpers.safe_merge_dicts(nested, custom_nested)
            flat = ecs_helpers.safe_merge_dicts(flat, custom_flat)
        new_nested = {}
        new_flat = {}
        if args.object:
            with open(args.object) as f:
                raw = yaml.safe_load(f.read())
                for (group, field) in nested.items():
                    inner_fields = field.pop('fields')
                    for (name, inner_field) in inner_fields.items():
                        for prefix in raw:
                            if inner_field['flat_name'].startswith(prefix):
                                new_nested.setdefault(group, field)
                                new_nested[group].setdefault('fields', {})
                                new_nested[group]['fields'][name] = inner_field
                
                for field_name in flat:
                    for prefix in raw:
                        if field_name.startswith(prefix):
                            new_flat[field_name] = flat[field_name]
                nested = new_nested
                flat = new_flat
            
    stripped_flat = {}
    retained_fields = ['description', 'example', 'type']
    for (name, field) in flat.items():
        stripped_flat[name] = {}
        for field_name in retained_fields:
            if field_name in field:
                stripped_flat[name][field_name] = field[field_name]

    ecs_helpers.yaml_dump('generated/ecs/ecs_stripped_flat.yml', stripped_flat)
    intermediate_files.generate(nested, flat)
    if args.intermediate_only:
        exit()

    csv_generator.generate(flat, ecs_version)
    es_template.generate(flat, ecs_version)
    if args.validate or args.object:
        exit()
    beats.generate(nested, ecs_version)
    asciidoc_fields.generate(nested, flat, ecs_version)


def argument_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument('--intermediate-only', action='store_true',
                        help='generate intermediary files only')
    parser.add_argument('--include', action='store',
                        help='include user specified directory of custom field definitions')
    parser.add_argument('--validate', action='store_true',
                        help='build user specified directory of custom field definitions and validate against ECS')
    parser.add_argument('--object', action='store',
                        help='build only fields with prefixes specified in object file')
    return parser.parse_args()


def read_version(file='version'):
    with open(file, 'r') as infile:
        return infile.read().rstrip()


if __name__ == '__main__':
    main()
