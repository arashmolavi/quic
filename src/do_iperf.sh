outfile=$1
host=$2

iperf3 -f Mbits -R -O 3 -J -c $host > $outfile"_iperf3.json"
