#!/bin/sh
### BEGIN INIT INFO
# Provides:          rgpio_pins.sh
# Required-Start:
# Required-Stop:
# Default-Start:     S
# Default-Stop:
# Short-Description: Creates links for rgpio in/dev/gpio
# Description:       rgpio is used to conect expternal Relay box with ModBus/RTU control
### END INIT INFO

nbunit=$(cat /data/rgpio/conf/units.conf)

# Kill existing rgpio service in case the script is called after HW configuration change:
kill $(ps | grep '{rgpio_service}' | grep -v grep | awk '{print $1}')

get_setting()                                                                                                                                                                                                  
        {                                                                                                                                                                                                      
                dbus-send --print-reply=literal --system --type=method_call --dest=com.victronenergy.settings $1 com.victronenergy.BusItem.GetValue | awk '/int32/ { print $3 }'                               
        }

# Clean existing gpio in case HW configuration has changed
rm -f /dev/gpio/relay_3
rm -f /dev/gpio/relay_4
rm -f /dev/gpio/relay_5
rm -f /dev/gpio/relay_6
rm -f /dev/gpio/relay_7
rm -f /dev/gpio/relay_8
rm -f /dev/gpio/relay_9
rm -f /dev/gpio/relay_a
rm -f /dev/gpio/relay_b
rm -f /dev/gpio/relay_c
rm -f /dev/gpio/relay_d
rm -f /dev/gpio/relay_e
rm -f /dev/gpio/relay_f
rm -f /dev/gpio/relay_g
rm -f /dev/gpio/relay_h
rm -f /dev/gpio/relay_i
rm -f /dev/gpio/digital_input_5
rm -f /dev/gpio/digital_input_6
rm -f /dev/gpio/digital_input_7
rm -f /dev/gpio/digital_input_8
rm -f /dev/gpio/digital_input_9
rm -f /dev/gpio/digital_input_a
rm -f /dev/gpio/digital_input_b
rm -f /dev/gpio/digital_input_c
rm -f /dev/gpio/digital_input_d
rm -f /dev/gpio/digital_input_e
rm -f /dev/gpio/digital_input_f
rm -f /dev/gpio/digital_input_g
rm -f /dev/gpio/digital_input_h
rm -f /dev/gpio/digital_input_i
rm -f /dev/gpio/digital_input_j
rm -f /dev/gpio/digital_input_k



if [ $nbunit = 1 ]
then
	#Relays
	ln -s /data/rgpio/sys/class/gpio/gpio103 /dev/gpio/relay_3
	ln -s /data/rgpio/sys/class/gpio/gpio104 /dev/gpio/relay_4
	ln -s /data/rgpio/sys/class/gpio/gpio105 /dev/gpio/relay_5
	ln -s /data/rgpio/sys/class/gpio/gpio106 /dev/gpio/relay_6
	ln -s /data/rgpio/sys/class/gpio/gpio107 /dev/gpio/relay_7
	ln -s /data/rgpio/sys/class/gpio/gpio108 /dev/gpio/relay_8
	ln -s /data/rgpio/sys/class/gpio/gpio109 /dev/gpio/relay_9
	ln -s /data/rgpio/sys/class/gpio/gpio110 /dev/gpio/relay_a

	#Digital_Inputs
	ln -s /data/rgpio/sys/class/gpio/gpio205 /dev/gpio/digital_input_5
	ln -s /data/rgpio/sys/class/gpio/gpio206 /dev/gpio/digital_input_6
	ln -s /data/rgpio/sys/class/gpio/gpio207 /dev/gpio/digital_input_7
	ln -s /data/rgpio/sys/class/gpio/gpio208 /dev/gpio/digital_input_8
	ln -s /data/rgpio/sys/class/gpio/gpio209 /dev/gpio/digital_input_9
	ln -s /data/rgpio/sys/class/gpio/gpio210 /dev/gpio/digital_input_a
	ln -s /data/rgpio/sys/class/gpio/gpio211 /dev/gpio/digital_input_b
	ln -s /data/rgpio/sys/class/gpio/gpio212 /dev/gpio/digital_input_c
fi

if [ $nbunit = 2 ]                                                
then                                                              
        #Relays                                                   
        ln -s /data/rgpio/sys/class/gpio/gpio103 /dev/gpio/relay_3
        ln -s /data/rgpio/sys/class/gpio/gpio104 /dev/gpio/relay_4
        ln -s /data/rgpio/sys/class/gpio/gpio105 /dev/gpio/relay_5
        ln -s /data/rgpio/sys/class/gpio/gpio106 /dev/gpio/relay_6
        ln -s /data/rgpio/sys/class/gpio/gpio107 /dev/gpio/relay_7
        ln -s /data/rgpio/sys/class/gpio/gpio108 /dev/gpio/relay_8
        ln -s /data/rgpio/sys/class/gpio/gpio109 /dev/gpio/relay_9
        ln -s /data/rgpio/sys/class/gpio/gpio110 /dev/gpio/relay_a
        ln -s /data/rgpio/sys/class/gpio/gpio111 /dev/gpio/relay_b
        ln -s /data/rgpio/sys/class/gpio/gpio112 /dev/gpio/relay_c
        ln -s /data/rgpio/sys/class/gpio/gpio113 /dev/gpio/relay_d
        ln -s /data/rgpio/sys/class/gpio/gpio114 /dev/gpio/relay_e        
        ln -s /data/rgpio/sys/class/gpio/gpio115 /dev/gpio/relay_f        
        ln -s /data/rgpio/sys/class/gpio/gpio116 /dev/gpio/relay_g        
        ln -s /data/rgpio/sys/class/gpio/gpio117 /dev/gpio/relay_h        
        ln -s /data/rgpio/sys/class/gpio/gpio118 /dev/gpio/relay_i        
                                                                          
        #Digital_Inputs                                                   
        ln -s /data/rgpio/sys/class/gpio/gpio205 /dev/gpio/digital_input_5
        ln -s /data/rgpio/sys/class/gpio/gpio206 /dev/gpio/digital_input_6
        ln -s /data/rgpio/sys/class/gpio/gpio207 /dev/gpio/digital_input_7
        ln -s /data/rgpio/sys/class/gpio/gpio208 /dev/gpio/digital_input_8
        ln -s /data/rgpio/sys/class/gpio/gpio209 /dev/gpio/digital_input_9
        ln -s /data/rgpio/sys/class/gpio/gpio210 /dev/gpio/digital_input_a
        ln -s /data/rgpio/sys/class/gpio/gpio211 /dev/gpio/digital_input_b
        ln -s /data/rgpio/sys/class/gpio/gpio212 /dev/gpio/digital_input_c
        ln -s /data/rgpio/sys/class/gpio/gpio213 /dev/gpio/digital_input_d
        ln -s /data/rgpio/sys/class/gpio/gpio214 /dev/gpio/digital_input_e
        ln -s /data/rgpio/sys/class/gpio/gpio215 /dev/gpio/digital_input_f
        ln -s /data/rgpio/sys/class/gpio/gpio216 /dev/gpio/digital_input_g
        ln -s /data/rgpio/sys/class/gpio/gpio217 /dev/gpio/digital_input_h
        ln -s /data/rgpio/sys/class/gpio/gpio218 /dev/gpio/digital_input_i
        ln -s /data/rgpio/sys/class/gpio/gpio219 /dev/gpio/digital_input_j
        ln -s /data/rgpio/sys/class/gpio/gpio220 /dev/gpio/digital_input_k
fi                



#Service
[ ! -f /service/rgpio ] && ln -s /data/RemoteGPIO/Workinprogress/service/rgpio /service/rgpio

#For managing reboot of DTWonder devices
nohup /data/RemoteGPIO/Workinprogress/rgpio_service &

exit 0
