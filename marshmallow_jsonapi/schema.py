# -*- coding: utf-8 -*-

import marshmallow as ma
from marshmallow.exceptions import ValidationError
from marshmallow.compat import iteritems, PY2

from .fields import BaseRelationship
from .exceptions import IncorrectTypeError
from .utils import resolve_params

TYPE = 'type'
ID = 'id'

def plain_function(f):
    """Ensure that ``callable`` is a plain function rather than an unbound method."""
    if PY2 and f:
        return f.im_func
    # Python 3 doesn't have bound/unbound methods, so don't need to do anything
    return f

class SchemaOpts(ma.SchemaOpts):

    def __init__(self, meta):
        super(SchemaOpts, self).__init__(meta)
        self.type_ = getattr(meta, 'type_', None)
        self.inflect = plain_function(getattr(meta, 'inflect', None))
        self.self_url = getattr(meta, 'self_url', None)
        self.self_url_kwargs = getattr(meta, 'self_url_kwargs', None)
        self.self_url_many = getattr(meta, 'self_url_many', None)
        self.included_schemas = getattr(meta, 'included_schemas', {})

class Schema(ma.Schema):
    """Schema class that formats data according to JSON API 1.0.
    Must define the ``type_`` `class Meta` option.

    Example: ::

        from marshmallow_jsonapi import Schema, fields

        def dasherize(text):
            return text.replace('_', '-')

        class PostSchema(Schema):
            id = fields.Str(dump_only=True)  # Required
            title = fields.Str()

            author = fields.HyperlinkRelated(
                '/authors/{author_id}',
                url_kwargs={'author_id': '<author.id>'},
            )

            comments = fields.HyperlinkRelated(
                '/posts/{post_id}/comments',
                url_kwargs={'post_id': '<id>'},
                # Include resource linkage
                many=True, include_data=True,
                type_='comments'
            )

            class Meta:
                type_ = 'posts'  # Required
                inflect = dasherize

    """
    class Meta:
        """Options object for `Schema`. Takes the same options as `marshmallow.Schema.Meta` with
        the addition of:
        - ``type_`` (required, the JSON API resource type as a string)
        - ``inflect`` (optional, an inflection function to modify attribute names)
        - ``self_url`` (optional, URL to use to `self` in links)
        - ``self_url_kwargs`` (optional, replacement fields for `self_url`.
          String arguments enclosed in `< >` will be interpreted as attributes
          to pull from the schema data.)
        - ``self_url_many`` (optional, URL to use to `self` in top-level `links`
            when a collection of resources is returned)
        """
        pass

    def __init__(self, *args, **kwargs):
        super(Schema, self).__init__(*args, **kwargs)

        if not self.opts.type_:
            raise ValueError('Must specify type_ class Meta option')

        if 'id' not in self.fields:
            raise ValueError('Must have an `id` field')

        if self.opts.self_url_kwargs and not self.opts.self_url:
            raise ValueError('Must specify `self_url` Meta option when '
                             '`self_url_kwargs` is specified')
        self.included_schemas = self.opts.included_schemas
        self.included_data = {}

    OPTIONS_CLASS = SchemaOpts

    @ma.post_dump(pass_many=True)
    def format_json_api_response(self, data, many):
        """Post-dump hook that formats serialized data as a top-level JSON API object.

        See: http://jsonapi.org/format/#document-top-level
        """
        ret = self.format_items(data, many)
        ret = self.wrap_response(ret, many)
        ret = self.render_included_data(ret)
        return ret

    def render_included_data(self, data):
        if not self.included_data:
            return data
        included = []
        for (type_, objId), value in self.included_data.items():
            if type_ not in self.included_schemas:
                raise ValueError('Must specify a schema in `included_schemas` for '
                                 'type ' + type_)
            schema = self.included_schemas[type_]
            result = schema.dump(value)
            if result.errors:
                raise ma.ValidationError(result.errors)
            included.append(result.data)
        data['included'] = included
        return data

    def unwrap_item(self, item):
        if 'type' not in item:
            raise ma.ValidationError('`data` object must include `type` key.')
        if item['type'] != self.opts.type_:
            raise IncorrectTypeError(actual=item['type'], expected=self.opts.type_)
        if 'attributes' not in item:
            raise ma.ValidationError('`data` object must include `attributes` key.')

        payload = self.dict_class()
        for key, value in iteritems(item.get('attributes', {})):
            payload[key] = value
        for key, value in iteritems(item.get('relationships', {})):
            payload[key] = value
        return payload

    @ma.pre_load(pass_many=True)
    def unwrap_request(self, data, many):
        if 'data' not in data:
            raise ma.ValidationError('Object must include `data` key.')

        data = data['data']
        if many:
            return [self.unwrap_item(each) for each in data]
        return self.unwrap_item(data)

    def on_bind_field(self, field_name, field_obj):
        """Schema hook override. When binding fields, set load_from to the
        inflected form of field_name.
        """
        if not field_obj.load_from:
            field_obj.load_from = self.inflect(field_name)
        return None

    # overrides ma.Schema._do_load so that we can format errors as JSON API Error objects.
    def _do_load(self, data, many=None, **kwargs):
        many = self.many if many is None else bool(many)
        try:
            result, errors = super(Schema, self)._do_load(data, many, **kwargs)
        except ValidationError as err:  # strict mode
            formatted_messages = self.format_errors(err.messages, many=many)
            err.messages = formatted_messages
            raise err
        else:
            formatted_messages = self.format_errors(errors, many=many)
        return result, formatted_messages

    def inflect(self, text):
        """Inflect ``text`` if the ``inflect`` class Meta option is defined, otherwise
        do nothing.
        """
        return self.opts.inflect(text) if self.opts.inflect else text

    ### Overridable hooks ###

    def format_errors(self, errors, many):
        """Format validation errors as JSON Error objects."""
        if not errors:
            return {}
        if isinstance(errors, (list, tuple)):
            return {'errors': errors}

        formatted_errors = []
        if many:
            for index, errors in iteritems(errors):
                for field_name, field_errors in iteritems(errors):
                    formatted_errors.extend([
                        self.format_error(field_name, message, index=index)
                        for message in field_errors
                    ])
        else:
            for field_name, field_errors in iteritems(errors):
                formatted_errors.extend([
                    self.format_error(field_name, message)
                    for message in field_errors
                ])
        return {'errors': formatted_errors}

    def format_error(self, field_name, message, index=None):
        """Override-able hook to format a single error message as an Error object.

        See: http://jsonapi.org/format/#error-objects
        """
        if isinstance(self.declared_fields.get(field_name), BaseRelationship):
            container = 'relationships'
        else:
            container = 'attributes'

        inflected_name = self.inflect(field_name)
        if index:
            pointer = '/data/{}/{}/{}'.format(index, container, inflected_name)
        else:
            pointer = '/data/{}/{}'.format(container, inflected_name)
        return {
            'detail': message,
            'source': {
                'pointer': pointer
            }
        }

    def format_item(self, item):
        """Format a single datum as a Resource object.

        See: http://jsonapi.org/format/#document-resource-objects
        """
        ret = self.dict_class()
        ret[TYPE] = self.opts.type_

        # Get the schema attributes so we can confirm `dump-to` values exist
        attributes = {
            (self.fields[field].dump_to or field): field
            for field in self.fields
        }

        for field_name, value in iteritems(item):
            attribute = attributes[field_name]
            if attribute == ID:
                ret[ID] = value
            elif isinstance(self.fields[attribute], BaseRelationship):
                if 'relationships' not in ret:
                    ret['relationships'] = self.dict_class()
                ret['relationships'][self.inflect(field_name)] = value
            else:
                if 'attributes' not in ret:
                    ret['attributes'] = self.dict_class()
                ret['attributes'][self.inflect(field_name)] = value

        links = self.get_resource_links(item)
        if links:
            ret['links'] = links
        return ret

    def format_items(self, data, many):
        """Format data as a Resource object or list of Resource objects.

        See: http://jsonapi.org/format/#document-resource-objects
        """
        if many:
            return [self.format_item(item) for item in data]
        else:
            return self.format_item(data)

    def get_top_level_links(self, data, many):
        """Hook for adding links to the root of the response data."""
        if many:
            if self.opts.self_url_many:
                return {'self': self.opts.self_url_many}
        else:
            if self.opts.self_url:
                self_link = data.get('links', {}).get('self', None)
                return {'self': self_link}

        return None

    def get_resource_links(self, item):
        """Hook for adding links to a resource object."""
        if self.opts.self_url:
            ret = self.dict_class()
            kwargs = resolve_params(item, self.opts.self_url_kwargs or {})
            ret['self'] = self.opts.self_url.format(**kwargs)
            return ret
        return None

    def wrap_response(self, data, many):
        """Wrap data and links according to the JSON API """
        ret = {'data': data}
        top_level_links = self.get_top_level_links(data, many)
        if top_level_links:
            ret['links'] = top_level_links
        return ret
