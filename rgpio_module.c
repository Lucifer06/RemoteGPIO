#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/gpio/driver.h>
#include <linux/platform_device.h>
#include <linux/irq.h>
#include <linux/irqdomain.h>

#define DRIVER_NAME "rgpio"
#define NUM_GPIOS 8

// Structure pour stocker les informations de notre driver
struct rgpio_chip {
    struct gpio_chip chip;
    struct platform_device *pdev;
    // Pour stocker les numéros d'IRQ virtuels associés à chaque GPIO
    unsigned int irqs[NUM_GPIOS]; 
};

// Fonction pour déclencher une interruption sur une ligne spécifique
static ssize_t trigger_irq_store(struct device *dev, struct device_attribute *attr, const char *buf, size_t count) {
    long line;
    int ret;
    struct rgpio_chip *rgpio = dev_get_drvdata(dev);

    ret = kstrtol(buf, 10, &line);
    if (ret) return ret;

    if (line < 0 || line >= NUM_GPIOS) {
        dev_err(dev, "Ligne invalide : %ld\n", line);
        return -EINVAL;
    }

    dev_info(dev, "Déclenchement de l'interruption virtuelle sur la ligne %ld\n", line);
    // On signale au noyau qu'une interruption s'est produite sur cette ligne
    generic_handle_irq(rgpio->irqs[line]);

    return count;
}

// Crée les attributs sysfs comme "trigger_irq" pour chaque ligne
#define RGPIO_ATTR(_name) __ATTR(_name, 0200, NULL, trigger_irq_store)
static struct device_attribute rgpio_attrs[] = {
    RGPIO_ATTR(trigger_irq),
};

static struct attribute *rgpio_chip_attrs[] = {
    &rgpio_attrs[0].attr,
    NULL,
};

static const struct attribute_group rgpio_chip_group = {
    .attrs = rgpio_chip_attrs,
};

// Initialisation du driver
static int rgpio_probe(struct platform_device *pdev) {
    struct rgpio_chip *rgpio;
    int i, ret;

    rgpio = devm_kzalloc(&pdev->dev, sizeof(*rgpio), GFP_KERNEL);
    if (!rgpio) return -ENOMEM;

    rgpio->chip.label = DRIVER_NAME;
    rgpio->chip.parent = &pdev->dev;
    rgpio->chip.owner = THIS_MODULE;
    rgpio->chip.base = -1; // Le noyau assigne la base
    rgpio->chip.ngpio = NUM_GPIOS;
    rgpio->chip.can_sleep = false;
    
    platform_set_drvdata(pdev, rgpio);

    // Crée un domaine d'interruption pour nos GPIOs virtuels
    struct irq_domain *irq_domain = irq_domain_create_linear(pdev->dev.fwnode, NUM_GPIOS, &irq_generic_chip_ops, NULL);
    if (!irq_domain) {
        dev_err(&pdev->dev, "Impossible de créer le domaine IRQ\n");
        return -ENOMEM;
    }

    // Associe une IRQ à chaque GPIO
    for (i = 0; i < NUM_GPIOS; i++) {
        rgpio->irqs[i] = irq_create_mapping(irq_domain, i);
    }
    
    // Ajoute la liaison entre le numéro de GPIO et le numéro d'IRQ
    ret = gpiochip_add_irqchip(&rgpio->chip, &irq_generic_chip, 0, handle_simple_irq, IRQ_TYPE_NONE);
    if (ret) {
        dev_err(&pdev->dev, "Impossible d'ajouter l'irqchip\n");
        return ret;
    }
    
    // Enregistre le gpio_chip auprès du noyau
    ret = devm_gpiochip_add_data(&pdev->dev, &rgpio->chip, rgpio);
    if (ret < 0) {
        dev_err(&pdev->dev, "Impossible d'enregistrer le gpiochip\n");
        return ret;
    }
    
    // Crée notre attribut sysfs "trigger_irq"
    ret = sysfs_create_group(&pdev->dev.kobj, &rgpio_chip_group);
    if (ret) {
        dev_err(&pdev->dev, "Impossible de créer le groupe sysfs\n");
    }

    dev_info(&pdev->dev, "Driver rgpio chargé, %d GPIOs créés à partir de la base %d\n", rgpio->chip.ngpio, rgpio->chip.base);
    return 0;
}

static struct platform_driver rgpio_driver = {
    .driver = { .name = DRIVER_NAME, },
    .probe = rgpio_probe,
};

static struct platform_device *rgpio_pdev;

// Fonction appelée lors du chargement du module
static int __init rgpio_init(void) {
    int ret;
    
    ret = platform_driver_register(&rgpio_driver);
    if (ret) return ret;

    rgpio_pdev = platform_device_alloc(DRIVER_NAME, -1);
    if (!rgpio_pdev) {
        platform_driver_unregister(&rgpio_driver);
        return -ENOMEM;
    }

    ret = platform_device_add(rgpio_pdev);
    if (ret) {
        platform_device_put(rgpio_pdev);
        platform_driver_unregister(&rgpio_driver);
        return ret;
    }

    return 0;
}

// Fonction appelée lors du déchargement
static void __exit rgpio_exit(void) {
    platform_device_unregister(rgpio_pdev);
    platform_driver_unregister(&rgpio_driver);
}

module_init(rgpio_init);
module_exit(rgpio_exit);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("Votre Nom");
MODULE_DESCRIPTION("Virtual GPIO driver for Victron Venus OS");
