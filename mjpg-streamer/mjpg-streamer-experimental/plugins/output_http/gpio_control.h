#ifndef GPIO_CONTROL_H
#define GPIO_CONTROL_H

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>

#define GPIO_PIN 597
#define GPIO_EXPORT "/sys/class/gpio/export"
#define GPIO_UNEXPORT "/sys/class/gpio/unexport"
#define GPIO_DIRECTION "/sys/class/gpio/gpio597/direction"
#define GPIO_VALUE "/sys/class/gpio/gpio597/value"

// Initialize GPIO pin
static inline int gpio_init(void) {
    int fd;
    char buffer[3];
    
    // Export GPIO pin
    fd = open(GPIO_EXPORT, O_WRONLY);
    if (fd < 0) {
        // Pin might already be exported
        // Continue anyway
    } else {
        sprintf(buffer, "%d", GPIO_PIN);
        write(fd, buffer, strlen(buffer));
        close(fd);
        usleep(100000); // Wait 100ms for sysfs to create the files
    }
    
    // Set direction to output
    fd = open(GPIO_DIRECTION, O_WRONLY);
    if (fd < 0) {
        perror("Failed to open GPIO direction");
        return -1;
    }
    write(fd, "out", 3);
    close(fd);
    
    return 0;
}

// Set GPIO value (0 or 1)
static inline int gpio_set_value(int value) {
    int fd;
    char buffer[2];
    
    fd = open(GPIO_VALUE, O_WRONLY);
    if (fd < 0) {
        perror("Failed to open GPIO value");
        return -1;
    }
    
    sprintf(buffer, "%d", value ? 1 : 0);
    write(fd, buffer, 1);
    close(fd);
    
    return 0;
}

// Get GPIO value
static inline int gpio_get_value(void) {
    int fd;
    char buffer[2];
    
    fd = open(GPIO_VALUE, O_RDONLY);
    if (fd < 0) {
        perror("Failed to open GPIO value for reading");
        return -1;
    }
    
    read(fd, buffer, 1);
    close(fd);
    
    return (buffer[0] == '1') ? 1 : 0;
}

// Cleanup GPIO
static inline void gpio_cleanup(void) {
    int fd;
    char buffer[3];
    
    fd = open(GPIO_UNEXPORT, O_WRONLY);
    if (fd >= 0) {
        sprintf(buffer, "%d", GPIO_PIN);
        write(fd, buffer, strlen(buffer));
        close(fd);
    }
}

#endif // GPIO_CONTROL_H
