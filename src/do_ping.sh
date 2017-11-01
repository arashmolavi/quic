outfile=$1
host=$2

ping -i 0.2 -c 100 $host > $outfile"_ping.txt"
