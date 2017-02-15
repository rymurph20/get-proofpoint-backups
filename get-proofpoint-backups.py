#
# Author  : Ryan Murphy (wwww.rmurph.com)
# Comment : This script will SSH into a Proofpoint server to get the most recent backup and move it to 
#           an acciesble Windows SMB share. The script user needs to have read/write access to the 
#           SMB share.
#
# Usage   : >>> proofpoint_getbackup.py
#
import os
import ssl
import paramiko
import re
import smtplib
import datetime as dtime

from email.mime.text import MIMEText
from datetime import datetime

def connect_ssh(server, username, password):
    """Connects to a server using SSH"""
    context = ssl.SSLContext(ssl.PROTOCOL_TLSv1)
    context.verify_mode = ssl.CERT_NONE

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(server, username=username, password=password)

    return ssh

def exec_ssh(ssh, cmd):
    """Executes a command using SSH and returns the result"""
    cmd = ssh.exec_command(cmd)

    result = {
        "stdin":cmd[0],
        "stdout":cmd[1],
        "stderr":cmd[2]
    }

    return result

def connect_scp(server, port, username, password):
    """Connects to a server using SCP"""
    scp = paramiko.Transport((server, port))
    scp.connect(username=username, password=password)
    scp = paramiko.SFTPClient.from_transport(scp)

    return scp

def send_smtp(smtp_server, smtp_to, smtp_from, smtp_subj, smtp_body):
    """Formats and sends an SMTP message"""
    msg = MIMEText(smtp_body, 'html')
    msg['Subject'] = smtp_subj
    msg['From'] = smtp_from
    msg['To'] = ", ".join(smtp_to)

    s = smtplib.SMTP(smtp_server)
    s.sendmail(smtp_from, smtp_to, msg.as_string())
    s.quit()

def main():

    # Proofpoint Info
    pp_server = 'PROOFPOINT.domain.com'
    pp_user = 'USERNAME'
    pp_pass = 'PASSWORD'
    pp_bkpdir = '/proofpoint/backup/dir'
    pp_lcldir = "\\\\domain.com\\share\\"
    scp_port = 22

    # SMTP Info (For email reports)
    smtp_server = 'SMTP.domain.com'
    smtp_from = 'username@domain.com'
    smtp_to = ['username@domain.com']

    # Date patterns to pull the date out of backup files
    date_rega = re.compile(r'\-(20\d{6})\.pbc$')
    date_regb = re.compile(r'^(20\d{6})\-')

    # Establish SSH Session to get current backups
    ssh = connect_ssh(pp_server, pp_user, pp_pass)
    scp = connect_scp(pp_server, scp_port, pp_user, pp_pass)
    result = exec_ssh(ssh, ("ls " + pp_bkpdir))

    # Rename files (date first) and sort by date
    i = 0
    backup_files = []
    for file in result["stdout"].readlines():
        backup_files.append([])
        backup_files[i].append(file.replace('\n', ''))

        for date in re.findall(date_rega, file):
            outfile = backup_files[i][0][:-13]
            outfile = date + "-" + outfile + ".pbc"

            backup_files[i].append(outfile)

            i += 1

    backup_files = sorted(backup_files, key=lambda x: x[1], reverse=True)
    ssh.close()

    scp.get((pp_bkpdir + backup_files[0][0]), (pp_lcldir + backup_files[0][1]), None)

    # Format HTML report for email
    smtp_body = '<Table width="75%" cellpadding="1" cellspacing="0" border="1">'
    smtp_body += '<td><b>Proofpoint Backup Report</b></td>'
    smtp_body += '<tr>'

    # Establish a datetime object X days in the past in order to compare backups to
    timeDelta = dtime.datetime.now() - dtime.timedelta(days=3)
    timeDelta = (str('{:04d}'.format(timeDelta.year)) + str('{:02d}'.format(timeDelta.month)) +
                str('{:02d}'.format(timeDelta.day)))
    timeDelta = datetime.strptime(timeDelta, '%Y%m%d')

    # Send an alert and not delete any more files if there are less than i files in the directory. This means
    # a backup has failed at some point.
    i = 3
    files = os.listdir(pp_lcldir)
    if len(files) < i:
        smtp_subj = 'Proofpoint Backup Report: Errors Detected'

        smtp_body += '<td><Font color="red">ERROR: Expected 3 backup files, got ' + str(len(files)) + '</font></td>'
    else:
        for file in files:  # Compare dates on PBC files. If the file is more than 3 days old it's removed.
            if file.endswith(".pbc"):
                for date in re.findall(date_regb, file):
                    fileDate = datetime.strptime(date, '%Y%m%d')

                if(fileDate < timeDelta):
                    os.remove(pp_lcldir + file)

        smtp_subj = 'Proofpoint Backup Report'
        smtp_body += '<td>Proofpoint backups are up-to-date.</td>'

    send_smtp(smtp_server, smtp_to, smtp_from, smtp_subj, smtp_body)

# Call main
if __name__ == "__main__":
   main()