#
# save_dashboard.py
#   Program to be run that can query grafana for a dashboard
#   and then save it in a way s.t. it can be re-loaded on sunsequent
#   runs of the system
#

import argparse
import os

# Mainloop
if __name__ == '__main__':

    #
    # Make the argument parser
    #

    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('--user', '-u', type=str,
                        metavar='GRAFANA_USER',
                        default=os.getenv("GRAFANA_USER", "admin"),
                        help='User to log into grafana with')
    parser.add_argument('--password', '-p', type=str,
                        metavar='GRAFANA_PASSWORD',
                        default=os.getenv("GRAFANA_PASSWORD", "admin"),
                        help='Password to log into grafana with')
    parser.add_argument('--serverurl', '-s', type=str,
                        metavar='GRAFANA_URL',
                        default=os.getenv('GRAFANA_URL', 'localhost:3001'),
                        help='Grafana server URL')
    parser.add_argument('--dashboard', '-d', type=str,
                        metavar='DASHBOARD_ID',
                        required=True,
                        help='ID of the dashboard to save')
    parser.add_argument('--name', '-n', type=str,
                        metavar='DASHBOARD_NAME',
                        required=True,
                        help='Name of the file under which to save the dashboard')
    parser.add_argument('--folder', '-f', type=str,
                        metavar='DASHBOARD_FOLDER',
                        default='/metrics/dashboard/user',
                        help='Folder in which to save the dashboard')

    #
    # Parse the arguments
    #

    args = parser.parse_args()
    print(args)
