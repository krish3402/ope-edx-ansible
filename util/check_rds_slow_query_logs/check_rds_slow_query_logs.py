from __future__ import absolute_import
from __future__ import print_function
import boto3
import click


def get_db_instances():

    """
    Returns:
          List of provisioned RDS instances
    """
    return rds.describe_db_instances()['DBInstances']

def get_db_clusters():

    """
    Returns:
          List of provisioned RDS instances
    """
    return rds.describe_db_clusters()['DBClusters']

def get_db_parameters(parameter_group_type, parameter_group_name, marker):

    """
    Returns:
           The detailed parameter list for a particular DB parameter
           group Using marker as pagination token as at max it returns
           100 records
    """

    if parameter_group_type == "instance":
        response = rds.describe_db_parameters(
                       DBParameterGroupName=parameter_group_name,
                       Marker=marker)
    elif parameter_group_type == "cluster":
        response = rds.describe_db_cluster_parameters(
                       DBClusterParameterGroupName=parameter_group_name,
                       Marker=marker)
    return response


def check_slow_query_logs(parameter_group_type, parameter_group_name):

    slow_log_enabled = False

    marker = ""

    while True:
        if marker is None:
            break

        response = get_db_parameters(parameter_group_type, parameter_group_name, marker)
        marker = response.get('Marker')
        parameters = response.get('Parameters')

        for param in parameters:
            if 'slow_query_log' in param['ParameterName']:
                if 'ParameterValue' in param and param['ParameterValue'] == '1':
                    slow_log_enabled = True
                break

    return slow_log_enabled


@click.command()
@click.option('--db_engine', help='Removed, left for compatibility')
@click.option('--whitelist', type=(str), multiple=True, help='Whitelisted RDS Instances')
def cli(db_engine, whitelist):

    ignore_rds =  list(whitelist)
    slow_query_logs_disabled_rds = []
    instances_out_of_sync_with_instance_parameters = []
    instances_out_of_sync_with_cluster_parameters = []
    exit_status = 0

    db_instances = get_db_instances()
    db_clusters = get_db_clusters()

    db_instance_parameter_groups = {}

    for instance in db_instances:
        db_identifier = instance['DBInstanceIdentifier']
        if db_identifier in ignore_rds or "test" in db_identifier:
            continue

        db_instance_parameter_groups[db_identifier] = {'instance': instance['DBParameterGroups'][0]}

    for cluster in db_clusters:
        for instance in cluster['DBClusterMembers']:
            db_identifier = instance['DBInstanceIdentifier']
            if db_identifier in ignore_rds or "test" in db_identifier:
                continue
            db_instance_parameter_groups[db_identifier]['cluster'] = cluster['DBClusterParameterGroup']

    for instance_name, parameter_groups in db_instance_parameter_groups.items():
        instance_parameter_group_name = parameter_groups['instance']['DBParameterGroupName']
        if parameter_groups['instance']['ParameterApplyStatus'] != "in-sync":
            instances_out_of_sync_with_instance_parameters.append(instance_name)
            exit_status = 1

        # First check if slow_query_logs are enabled in the instance parameter group which takes precedence over the cluster
        # level parameter group
        slow_query_logs_enabled = check_slow_query_logs('instance', instance_parameter_group_name)

        if 'cluster' in parameter_groups.keys():
            cluster_parameter_group_name = parameter_groups['cluster']
            # If slow query logs weren't enabled by a cluster level parameter, see if they are enabled at the instance level
            if not slow_query_logs_enabled:
                slow_query_logs_enabled = check_slow_query_logs('cluster', cluster_parameter_group_name)

        if not slow_query_logs_enabled:
            exit_status = 1
            slow_query_logs_disabled_rds.append(db_identifier)

    print(("Slow query logs are disabled for RDS Instances\n{0}".format(slow_query_logs_disabled_rds)))
    print()
    print(("Instance parameter groups out of sync/pending reboot for RDS Instances\n{0}".format(instances_out_of_sync_with_instance_parameters)))
    print()
    print(("Cluster parameter groups out of sync/pending reboot for RDS Instances\n{0}".format(instances_out_of_sync_with_instance_parameters)))
    exit(exit_status)

if __name__ == '__main__':

    rds = boto3.client('rds')
    cli()