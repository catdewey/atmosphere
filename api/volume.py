"""
Atmosphere service volume
"""
from django.utils.timezone import datetime

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from libcloud.common.types import InvalidCredsError

from threepio import logger


from core.models.instance import convert_esh_instance
from core.models.provider import AccountProvider
from core.models.volume import convert_esh_volume

from service.volume import create_volume, boot_volume
from service.exceptions import OverQuotaError

from api import prepare_driver, failure_response, invalid_creds
from api.permissions import InMaintenance, ApiAuthRequired
from api.serializers import VolumeSerializer


class VolumeSnapshot(APIView):
    """
    Initialize and view volume snapshots
    """
    permission_classes = (ApiAuthRequired,)
    
    def get(self, request, provider_id, identity_id):
        """
        """
        user = request.user
        esh_driver = prepare_driver(request, provider_id, identity_id)
        if not esh_driver:
            return invalid_creds(provider_id, identity_id)
        esh_snapshots = esh_driver._connection.ex_list_snapshots()
        snapshot_data = []
        for ss in esh_snapshots:
            snapshot_data.append({
                'id': ss.id,
                'name': ss.extra['name'],
                'size': ss.size,
                'description': ss.extra['description'],
                'created': ss.extra['created'],
                'status': ss.extra['status'],
                'volume_id': ss.extra['volume_id'],})

        response = Response(snapshot_data)
        return response

    def post(self, request, provider_id, identity_id):
        """
        Updates DB values for volume
        """
        user = request.user
        data = request.DATA

        missing_keys = valid_snapshot_post_data(data)
        if missing_keys:
            return keys_not_found(missing_keys)
        #Required
        size = data.get('size')
        volume_id = data.get('volume_id')
        display_name = data.get('display_name')
        #Optional
        description = data.get('description')
        metadata = data.get('metadata')
        snapshot_id = data.get('snapshot_id')

        #STEP 0 - Existence tests
        esh_driver = prepare_driver(request, provider_id, identity_id)
        if not esh_driver:
            return invalid_creds(provider_id, identity_id)
        esh_volume = esh_driver.get_volume(volume_id)
        #TODO: Put quota tests at the TOP so we dont over-create resources!
        #STEP 1 - Reuse/Create snapshot
        if snapshot_id:
            snapshot = esh_driver._connection.get_snapshot(snapshot_id)
            if not snapshot:
                return failure_response(
                    status.HTTP_400_BAD_REQUEST,
                    "Snapshot %s not found. Process aborted."
                    % snapshot_id)
        else:
            #Normal flow, create a snapshot from the volume
            if not esh_volume:
                return volume_not_found(volume_id)
            if esh_volume.extra['status'].lower() != 'available':
               return failure_response(
                       status.HTTP_400_BAD_REQUEST,
                       "Volume status must be 'available'. "
                       "Did you detach the volume?")

            snapshot = esh_driver._connection.ex_create_snapshot(
                    esh_volume, display_name, description)
            if not snapshot:
                return failure_response(
                    status.HTTP_400_BAD_REQUEST,
                    "Snapshot not created. Process aborted.")
        #STEP 2 - Create volume from snapshot
        try:
            success, esh_volume = create_volume(esh_driver, identity_id,
                                                display_name, size,
                                                description, metadata,
                                                snapshot=snapshot)
            if not success:
                return failure_response(
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    'Volume creation failed. Contact support')
            # Volume creation succeeded
            core_volume = convert_esh_volume(esh_volume, provider_id,
                                             identity_id, user)
            serialized_data = VolumeSerializer(core_volume,
                                               context={'request':request}).data
            return Response(serialized_data, status=status.HTTP_201_CREATED)
        except OverQuotaError, oqe:
            return over_quota(oqe)
        except InvalidCredsError:
            return invalid_creds(provider_id, identity_id)

class VolumeSnapshotDetail(APIView):
    """Details of specific volume on Identity."""
    permission_classes = (ApiAuthRequired,)
    
    def get(self, request, provider_id, identity_id, snapshot_id):
        """
        """
        user = request.user
        esh_driver = prepare_driver(request, provider_id, identity_id)
        if not esh_driver:
            return invalid_creds(provider_id, identity_id)
        snapshot = esh_driver._connection.get_snapshot(snapshot_id)
        if not snapshot:
            return snapshot_not_found(snapshot_id)
        response = Response(snapshot)
        return response

    def delete(self, request, provider_id, identity_id, snapshot_id):
        """
        Destroys the volume and updates the DB
        """
        user = request.user
        #Ensure volume exists
        esh_driver = prepare_driver(request, provider_id, identity_id)
        if not esh_driver:
            return invalid_creds(provider_id, identity_id)
        snapshot = esh_driver._connection.get_snapshot(snapshot_id)
        if not snapshot:
            return snapshot_not_found(snapshot_id)
        delete_success = esh_driver._connection.ex_delete_snapshot(snapshot)
        #NOTE: Always false until icehouse...
        #if not delete_success:
        #    return failure_response(
        #        status.HTTP_400_BAD_REQUEST,
        #        "Failed to delete snapshot %s. Please try again later."
        #        % snapshot_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class VolumeList(APIView):
    """List all volumes on Identity"""

    permission_classes = (ApiAuthRequired,)

    def get(self, request, provider_id, identity_id):
        """
        Retrieves list of volumes and updates the DB
        """
        user = request.user
        esh_driver = prepare_driver(request, provider_id, identity_id)
        if not esh_driver:
            return invalid_creds(provider_id, identity_id)
        volume_list_method = esh_driver.list_volumes

        if AccountProvider.objects.filter(identity__id=identity_id):
            # Instance list method changes when using the OPENSTACK provider
            volume_list_method = esh_driver.list_all_volumes

        esh_volume_list = volume_list_method()

        core_volume_list = [convert_esh_volume(volume, provider_id,
                                               identity_id, user)
                            for volume in esh_volume_list]
        serializer = VolumeSerializer(core_volume_list,
                                      context={'request':request}, many=True)
        response = Response(serializer.data)
        return response

    def post(self, request, provider_id, identity_id):
        """
        Creates a new volume and adds it to the DB
        """
        user = request.user
        esh_driver = prepare_driver(request, provider_id, identity_id)
        if not esh_driver:
            return invalid_creds(provider_id, identity_id)
        data = request.DATA
        missing_keys = valid_create_data(data)
        if missing_keys:
            return keys_not_found(missing_keys)
        #Pass arguments
        name = data.get('name')
        size = data.get('size')
        #Optional fields
        description = data.get('description')
        image_id = data.get('image')
        if image_id:
            image = driver.get_machine(image_id)
            image_size = image._connection.get_size(image._image)
            if int(size) > image_size + 4:
                return failure_response(
                    status.HTTP_400_BAD_REQUEST,
                    "Volumes created from images can be no more than 4GB larger "
                    " than the size of the image: %s GB" % image_size)
        snapshot_id = data.get('snapshot')
        if snapshot_id:
            snapshot = driver._connection.ex_get_snapshot(image_id)
        else:
            snapshot = None
        try:
            success, esh_volume = create_volume(esh_driver, identity_id,
                                                name, size, description,
                                                snapshot=snapshot, image=image)
        except OverQuotaError, oqe:
            return over_quota(oqe)
        except InvalidCredsError:
            return invalid_creds(provider_id, identity_id)
        if not success:
            return failure_response(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                'Volume creation failed. Contact support')
        # Volume creation succeeded
        core_volume = convert_esh_volume(esh_volume, provider_id,
                                         identity_id, user)
        serialized_data = VolumeSerializer(core_volume,
                                           context={'request':request}).data
        return Response(serialized_data, status=status.HTTP_201_CREATED)


class Volume(APIView):
    """Details of specific volume on Identity."""
    permission_classes = (ApiAuthRequired,)
    
    def get(self, request, provider_id, identity_id, volume_id):
        """
        """
        user = request.user
        esh_driver = prepare_driver(request, provider_id, identity_id)
        if not esh_driver:
            return invalid_creds(provider_id, identity_id)
        esh_volume = esh_driver.get_volume(volume_id)
        if not esh_volume:
            return volume_not_found(volume_id)
        core_volume = convert_esh_volume(esh_volume, provider_id,
                                         identity_id, user)
        serialized_data = VolumeSerializer(core_volume,
                                           context={'request':request}).data
        response = Response(serialized_data)
        return response

    def patch(self, request, provider_id, identity_id, volume_id):
        """
        Updates DB values for volume
        """
        user = request.user
        data = request.DATA
        #Ensure volume exists
        esh_driver = prepare_driver(request, provider_id, identity_id)
        if not esh_driver:
            return invalid_creds(provider_id, identity_id)
        esh_volume = esh_driver.get_volume(volume_id)
        if not esh_volume:
            return volume_not_found(volume_id)
        core_volume = convert_esh_volume(esh_volume, provider_id,
                                         identity_id, user)
        serializer = VolumeSerializer(core_volume, data=data, 
                                      context={'request':request},
                                      partial=True)
        if serializer.is_valid():
            serializer.save()
            response = Response(serializer.data)
            return response
        else:
            return failure_response(
                status.HTTP_400_BAD_REQUEST,
                serializer.errors)

    def put(self, request, provider_id, identity_id, volume_id):
        """
        Updates DB values for volume
        """
        user = request.user
        data = request.DATA
        #Ensure volume exists
        esh_driver = prepare_driver(request, provider_id, identity_id)
        if not esh_driver:
            return invalid_creds(provider_id, identity_id)
        esh_volume = esh_driver.get_volume(volume_id)
        if not esh_volume:
            return volume_not_found(volume_id)
        core_volume = convert_esh_volume(esh_volume, provider_id,
                                         identity_id, user)
        serializer = VolumeSerializer(core_volume, data=data,
                                      context={'request':request},
                
                )
        if serializer.is_valid():
            serializer.save()
            response = Response(serializer.data)
            return response
        else:
            failure_response(
                status.HTTP_400_BAD_REQUEST,
                serializer.errors)

    def delete(self, request, provider_id, identity_id, volume_id):
        """
        Destroys the volume and updates the DB
        """
        user = request.user
        #Ensure volume exists
        esh_driver = prepare_driver(request, provider_id, identity_id)
        if not esh_driver:
            return invalid_creds(provider_id, identity_id)
        esh_volume = esh_driver.get_volume(volume_id)
        if not esh_volume:
            return volume_not_found(volume_id)
        core_volume = convert_esh_volume(esh_volume, provider_id,
                                         identity_id, user)
        #Delete the object, update the DB
        esh_driver.destroy_volume(esh_volume)
        core_volume.end_date = datetime.now()
        core_volume.save()
        #Return the object
        serialized_data = VolumeSerializer(core_volume,
                                           context={'request':request},
                
                ).data
        response = Response(serialized_data)
        return response


class BootVolume(APIView):
    """Launch an instance using this volume as the source"""
    permission_classes = (ApiAuthRequired,)

    def _select_source(self, esh_driver, data):
        source_id = source_type = get_source = None
        if 'image_id' in data:
            source_type = "image"
            source_id = data.pop('image_id')
            get_source = esh_driver.get_machine
        elif 'snapshot_id' in data:
            source_type = "snapshot"
            source_id = data.pop('snapshot_id')
            get_source = esh_driver._connection.ex_get_snapshot
        elif 'volume_id' in data:
            source_type = "volume"
            source_id = data.pop('volume_id')
        else:
            source_type = "volume"
            source_id = volume_id
            get_source = esh_driver.get_volume
        return (source_type, get_source, source_id)
    
    def post(self, request, provider_id, identity_id, volume_id=None):
        user = request.user
        data = request.DATA

        missing_keys = valid_launch_data(data)
        if missing_keys:
            return keys_not_found(missing_keys)

        esh_driver = prepare_driver(request, provider_id, identity_id)
        if not esh_driver:
            return invalid_creds(provider_id, identity_id)

        source = None
        name = data.pop('name')
        size_id = data.pop('size')

        (source_type, get_source, source_id) = self._select_source(esh_driver, data)
        if not get_source:
            return failure_response(
                    status.HTTP_400_BAD_REQUEST, 
                    'Source could not be acquired. Did you send: ['
                    'snapshot_id/volume_id/image_id] ?')
        source = get_source(source_id)
        if not source:
            return failure_response(
                status.HTTP_404_NOT_FOUND,
                "%s %s does not exist"
                % (source_type.title(),source_id))
        size = esh_driver.get_size(size_id)
        if not size:
            return failure_response(
                status.HTTP_404_NOT_FOUND,
                "Size %s does not exist"
                % (size_id,))

        esh_instance = boot_volume(esh_driver, identity_id, name, size, source, source_type, **data)
        core_instance = convert_esh_instance(esh_driver, esh_instance,
                                             provider_id, identity_id, user)
        serialized_data = InstanceSerializer(core_instance,
                                             context={'request':request}).data
        response = Response(serialized_data)
        return response


def valid_launch_data(data):
    """
    Return any missing required post key names.
    """
    required = ['name', 'size']
    return [key for key in required
            #Key must exist and have a non-empty value.
            if key not in data or (type(data[key]) == str and len(data[key]) > 0)]


def valid_snapshot_post_data(data):
    """
    Return any missing required post key names.
    """
    required = ['display_name', 'volume_id', 'size']
    return [key for key in required
            #Key must exist and have a non-empty value.
            if key not in data or (type(data[key]) == str and len(data[key]) > 0)]
def valid_create_data(data):
    """
    Return any missing required post key names.
    """
    required = ['name', 'size']
    return [key for key in required
            #Key must exist and have a non-empty value.
            if key not in data or (type(data[key]) == str and len(data[key]) > 0)]


def keys_not_found(missing_keys):
    return failure_response(
        status.HTTP_400_BAD_REQUEST,
        'Missing required POST datavariables : %s' % missing_keys)


def snapshot_not_found(snapshot_id):
    return failure_response(
        status.HTTP_404_NOT_FOUND,
        'Snapshot %s does not exist' % snapshot_id)


def volume_not_found(volume_id):
    return failure_response(
        status.HTTP_404_NOT_FOUND,
        'Volume %s does not exist' % volume_id)


def over_quota(quota_exception):
    return failure_response(
        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        quota_exception.message)
