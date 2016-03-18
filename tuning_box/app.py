# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import itertools

import flask
import flask_restful
from flask_restful import fields
from werkzeug import exceptions
from werkzeug import routing
from werkzeug import urls

from tuning_box import db

api = flask_restful.Api()

resource_definition_fields = {
    'id': fields.Integer,
    'name': fields.String,
    'component_id': fields.Integer,
    'content': fields.Raw,
}

component_fields = {
    'id': fields.Integer,
    'name': fields.String,
    'resource_definitions': fields.List(
        fields.Nested(resource_definition_fields)),
}


@api.resource('/components', '/components/<int:component_id>')
class Component(flask_restful.Resource):
    method_decorators = [flask_restful.marshal_with(component_fields)]

    def get(self, component_id=None):
        if component_id is None:
            return db.Component.query.all()
        else:
            return db.Component.query.get_or_404(component_id)

    def post(self):
        component = db.Component(name=flask.request.json['name'])
        component.resource_definitions = []
        for resdef_data in flask.request.json.get('resource_definitions'):
            resdef = db.ResourceDefinition(name=resdef_data['name'],
                                           content=resdef_data['content'])
            component.resource_definitions.append(resdef)
        db.db.session.add(component)
        db.db.session.commit()
        return component, 201

    def delete(self, component_id):
        component = db.Component.query.get_or_404(component_id)
        db.db.session.delete(component)
        db.db.session.commit()
        return None, 204

environment_fields = {
    'id': fields.Integer,
    'components': fields.List(fields.Integer(attribute='id')),
    'hierarchy_levels': fields.List(fields.String(attribute='name')),
}


@api.resource('/environments', '/environments/<int:environment_id>')
class Environment(flask_restful.Resource):
    method_decorators = [flask_restful.marshal_with(environment_fields)]

    def get(self, environment_id=None):
        if environment_id is None:
            return db.Environment.query.all()
        else:
            return db.Environment.query.get_or_404(environment_id)

    def post(self):
        component_ids = flask.request.json['components']
        components = [db.Component.query.get_or_404(i) for i in component_ids]

        hierarchy_levels = []
        level = None
        for name in flask.request.json['hierarchy_levels']:
            level = db.EnvironmentHierarchyLevel(name=name, parent=level)
            hierarchy_levels.append(level)

        environment = db.Environment(components=components,
                                     hierarchy_levels=hierarchy_levels)
        db.db.session.add(environment)
        db.db.session.commit()
        return environment, 201

    def delete(self, environment_id):
        environment = db.Environment.query.get_or_404(environment_id)
        db.db.session.delete(environment)
        db.db.session.commit()
        return None, 204


class LevelsConverter(routing.BaseConverter):
    """Converter that maps nested levels to list of tuples.

    For example, "level1/value1/level2/value2/" is mapped to
    [("level1", "value1"), ("level2", "value2")].

    Note that since it can be empty it includes following "/":

        Rule('/smth/<levels:levels>values')

    will parse "/smth/values" and "/smth/level1/value1/values".
    """

    regex = "([^/]+/[^/]+/)*"

    def to_python(self, value):
        spl = value.split('/')
        return list(zip(spl[::2], spl[1::2]))

    def to_url(self, value):
        parts = itertools.chain.from_iterable(value)
        quoted_parts = (urls.url_quote(p, charset=self.map.charset, safe='')
                        for p in parts)
        return ''.join(p + '/' for p in quoted_parts)


def iter_environment_level_values(environment, levels):
    env_levels = db.EnvironmentHierarchyLevel.get_for_environment(environment)
    level_pairs = itertools.chain(
        [(None, (None, None))],  # root level
        zip(env_levels, levels),
    )
    parent_level_value = None
    for env_level, (level_name, level_value) in level_pairs:
        if env_level:
            if env_level.name != level_name:
                raise exceptions.BadRequest(
                    "Unexpected level name '%s'. Expected '%s'." % (
                        level_name, env_level.name))
        level_value_db = db.get_or_create(
            db.EnvironmentHierarchyLevelValue,
            level=env_level,
            parent=parent_level_value,
            value=level_value,
        )
        yield level_value_db
        parent_level_value = level_value_db


def get_environment_level_value(environment, levels):
    for level_value in iter_environment_level_values(environment, levels):
        pass
    return level_value


@api.resource(
    '/environments/<int:environment_id>' +
    '/<levels:levels>resources/<int:resource_id>/values')
class ResourceValues(flask_restful.Resource):
    def put(self, environment_id, levels, resource_id):
        environment = db.Environment.query.get_or_404(environment_id)
        # TODO(yorik-sar): filter by environment
        resdef = db.ResourceDefinition.query.get_or_404(resource_id)
        level_value = get_environment_level_value(environment, levels)
        esv = db.get_or_create(
            db.ResourceValues,
            environment=environment,
            resource_definition=resdef,
            level_value=level_value,
        )
        esv.values = flask.request.json
        db.db.session.commit()
        return None, 204

    def get(self, environment_id, resource_id, levels):
        environment = db.Environment.query.get_or_404(environment_id)
        # TODO(yorik-sar): filter by environment
        resdef = db.ResourceDefinition.query.get_or_404(resource_id)
        level_values = list(iter_environment_level_values(environment, levels))
        resource_values = db.ResourceValues.query.filter_by(
            resource_definition=resdef,
            environment=environment,
        ).all()
        result = {}
        for level_value in level_values:
            for resource_value in resource_values:
                if resource_value.level_value == level_value:
                    result.update(resource_value.values)
                    break
        return result


def build_app():
    app = flask.Flask(__name__)
    app.url_map.converters['levels'] = LevelsConverter
    api.init_app(app)  # init_app spoils Api object if app is a blueprint
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False  # silence warning
    db.db.init_app(app)
    return app


def main():
    import logging
    logging.basicConfig(level=logging.DEBUG)

    app = build_app()
    app.run()

if __name__ == '__main__':
    main()
