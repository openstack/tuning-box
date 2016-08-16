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

from tuning_box import errors


class KeysOperationMixin(object):

    OPERATION_SET = 'set'
    OPERATION_DELETE = 'delete'

    OPERATIONS = (OPERATION_SET, OPERATION_DELETE)

    def _check_out_of_index(self, cur_point, key, keys_path):
        if isinstance(cur_point, (list, tuple)) and key >= len(cur_point):
            raise errors.KeysPathNotExisted(
                "Keys path doesn't exist {0}. "
                "Failed on the key {1}".format(keys_path, key)
            )

    def _check_key_existed(self, cur_point, key, keys_path):
        if isinstance(cur_point, dict) and key not in cur_point:
            raise errors.KeysPathNotExisted(
                "Keys path doesn't exist {0}. "
                "Failed on the key {1}".format(keys_path, key)
            )

    def _check_path_is_reachable(self, cur_point, key, keys_path):
        if not isinstance(cur_point, (list, tuple, dict)):
            raise errors.KeysPathUnreachable(
                "Leaf value {0} found on key {1} "
                "in keys path {2}".format(cur_point, key, keys_path)
            )

    def do_set(self, storage, keys_paths):
        """Sets values from keys paths to storage.

        Keys path is list of keys paths. If we have keys_paths
        [['a', 'b', 'val']], then storage['a']['b'] will be set to 'val'.
        Last value in the keys path is value to be set.

        :param storage: data
        :param keys_paths: lists of keys paths to be set
        """

        for keys_path in keys_paths:
            cur_point = storage
            if len(keys_path) < 2:
                raise errors.KeysPathInvalid(
                    "Keys path {0} invalid. Keys path should contains "
                    "at least one key and value".format(keys_path)
                )

            for key in keys_path[:-2]:
                self._check_path_is_reachable(cur_point, key, keys_path)
                self._check_out_of_index(cur_point, key, keys_path)
                self._check_key_existed(cur_point, key, keys_path)
                cur_point = cur_point[key]

            assign_to = keys_path[-2]
            self._check_out_of_index(cur_point, assign_to, keys_path)
            cur_point[assign_to] = keys_path[-1]

    def do_delete(self):
        pass

    def perform_operation(self, operation, storage, keys_paths):
        if operation == self.OPERATION_SET:
            self.do_set(storage, keys_paths)
        elif operation == self.OPERATION_DELETE:
            pass
        else:
            raise errors.UnknownKeysOperation(
                "Unknown operation: {0}. "
                "Allowed operations: {1}".format(operation, self.OPERATIONS)
            )
