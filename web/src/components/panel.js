import React from 'react'
import styles from './panel.sass'

export default class Panel extends React.Component {
    constructor(...args) {
        super(...args)
    }

    render() {
        return <div className={styles.panel}>
            {this.props.children}
        </div>
    }
}